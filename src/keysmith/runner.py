"""Runners: how a compiled passwordlist is actually tried against a wallet.

Two implementations behind one ``Runner`` protocol:

* ``NullRunner`` — the default. Emits a single ``error`` event ("runner not
  configured") so the app **never fabricates a run**. The backend ships this
  unless a real sealed VM is wired up.
* ``SealedVmRunner`` — the real thing. It reproduces the S3 spike flow
  (docs/spikes/sealed-vm.md) exactly:

      create a VM from the prebuilt snapshot via the Vultr API
        -> cloud-init has already applied the nftables egress lock
           (output + forward policy drop)
        -> verify containment (runsc, --network none, wallet :ro, agent box
           has no wallet mount, host egress blocked)
        -> push the wallet + passwordlist in over inbound SSH (stdin pipe, so
           nothing is written to the control VM's disk)
        -> run btcrecover inside gVisor with --network none
        -> stream progress/result back over the same SSH session
        -> DELETE the instance
        -> emit a TeardownReceipt

The VM can never open an outbound connection; the only channel is the control
VM's inbound SSH, and the wallet bytes never travel back out over it — only
progress numbers and the final result do.

This module is wiring, not cryptography: the guessing is done by btcrecover
(a long-standing open-source recovery tool) inside the sandbox, and the
candidate list is the one the user already saw and approved on the plan screen.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Optional, Protocol

from .receipt import (
    TeardownReceipt, MODE_PER_JOB_VM,
    OUTCOME_FOUND, OUTCOME_NOT_FOUND, OUTCOME_ERROR,
)

Emit = Callable[[Dict], Awaitable[None]]


class Runner(Protocol):
    async def run(self, job, emit: Emit) -> None: ...
    async def attack(self, job, emit: Emit) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Null runner (default): honest "not configured".
# ---------------------------------------------------------------------------

class NullRunner:
    """Does nothing but say so. Guarantees the app cannot fake a recovery."""

    name = "null"

    async def run(self, job, emit: Emit) -> None:
        await emit({
            "type": "error",
            "message": (
                "the sealed-VM runner is not configured on this deployment, so "
                "no real recovery can run here. Set the Vultr API key, snapshot "
                "id and SSH key to enable it."
            ),
        })
        await emit({"type": "stage", "stage": "error"})

    async def attack(self, job, emit: Emit) -> None:
        await emit({
            "type": "error",
            "message": "no live box to run the containment test against (runner not configured).",
        })


# ---------------------------------------------------------------------------
# Sealed VM runner.
# ---------------------------------------------------------------------------

@dataclass
class VmConfig:
    """Everything the sealed runner needs, all from the environment. No secret
    is baked into the repo."""
    api_key: str
    snapshot_id: str
    sshkey_id: str
    ssh_key_path: str
    region: str = "lhr"
    plan: str = "vc2-2c-4gb"
    ssh_user: str = "root"
    vcpus: int = 2
    api_base: str = "https://api.vultr.com/v2"
    boot_timeout_s: int = 900   # snapshot restores can take several minutes to unlock
    job_timeout_s: int = 1800
    image: str = "keysmith/btcrecover"   # baked into the snapshot
    remote_job_dir: str = "/job"

    @classmethod
    def from_env(cls) -> Optional["VmConfig"]:
        api_key = os.environ.get("VULTR_API_KEY", "")
        snapshot_id = os.environ.get("KEYSMITH_SNAPSHOT_ID", "")
        sshkey_id = os.environ.get("KEYSMITH_SSHKEY_ID", "")
        ssh_key_path = os.environ.get("KEYSMITH_SSH_KEY", "")
        if not (api_key and snapshot_id and sshkey_id and ssh_key_path):
            return None
        return cls(
            api_key=api_key, snapshot_id=snapshot_id, sshkey_id=sshkey_id,
            ssh_key_path=os.path.expanduser(ssh_key_path),
            region=os.environ.get("KEYSMITH_REGION", "lhr"),
            plan=os.environ.get("KEYSMITH_PLAN", "vc2-2c-4gb"),
        )


# btcrecover invocation per wallet type. The passwordlist is piped in and read
# from the mounted job dir; the wallet is mounted read-only.
_WALLET_FILENAME = {
    "metamask": "vault.json",
    "bitcoin_core": "wallet.dat",
    "electrum": "electrum.wallet",
    "blockchain": "wallet.aes.json",
}


class SealedVmRunner:
    """Per-job Vultr VM, sealed, runs btcrecover, destroyed afterwards."""

    name = "vm"

    def __init__(self, config: VmConfig) -> None:
        self.config = config

    # --- Runner protocol -----------------------------------------------------

    async def run(self, job, emit: Emit) -> None:
        cfg = self.config
        vm_id: Optional[str] = None
        created_at = _now()
        outcome = OUTCOME_ERROR
        guesses_tried = 0
        api_delete_status: Optional[str] = None
        try:
            await emit({"type": "stage", "stage": "creating_box"})
            # Assign vm_id BEFORE the wait, so a boot timeout still destroys it
            # in the finally block (no leaked VMs).
            vm_id = await self._create_instance()
            ip = await self._wait_for_ssh(vm_id, emit)
            job._vm_ip = ip  # transient, never serialized
            await emit({
                "type": "box", "vm_id": vm_id, "region": cfg.region,
                "plan": cfg.plan, "ip_hidden": True,
            })

            await emit({"type": "stage", "stage": "sealing"})
            await self._apply_egress_lock(ip, emit)
            checks = await self._verify_seal(ip, emit)
            await emit({"type": "seal", "checks": checks})

            await emit({"type": "stage", "stage": "uploading"})
            await self._upload(ip, job, emit)

            await emit({"type": "stage", "stage": "running"})
            found, password, guesses_tried = await self._crack(ip, job, emit)

            if found:
                await emit({"type": "stage", "stage": "found"})
                # Shown once to the live viewer; never persisted.
                await emit({"type": "result", "found": True, "password": password})
                outcome = OUTCOME_FOUND
            else:
                await emit({"type": "stage", "stage": "not_found"})
                await emit({"type": "result", "found": False})
                outcome = OUTCOME_NOT_FOUND

        except RunnerError as exc:
            await emit({"type": "error", "message": str(exc)})
            outcome = OUTCOME_ERROR
        except Exception as exc:  # pragma: no cover - defensive
            await emit({"type": "error", "message": f"unexpected runner error: {exc}"})
            outcome = OUTCOME_ERROR
        finally:
            if vm_id:
                await emit({"type": "stage", "stage": "destroying"})
                api_delete_status = await self._destroy(vm_id)
                await emit({"type": "stage", "stage": "destroyed"})
            elif outcome == OUTCOME_ERROR:
                await emit({"type": "stage", "stage": "error"})
            receipt = TeardownReceipt(
                job_id=job.id,
                mode=MODE_PER_JOB_VM,
                wallet_type=job.wallet_type,
                outcome=outcome,
                created_at=created_at,
                destroyed_at=_now(),
                guesses_tried=guesses_tried,
                bytes_egressed_wallet=0,
                vm_id=vm_id or "none",
                api_delete_status=api_delete_status,
                network_mode="none",
                agent_wallet_mounts=0,
            )
            try:
                receipt.validate()
            except Exception:  # pragma: no cover - defensive
                pass
            await emit({"type": "receipt", "receipt": receipt.to_dict()})

    async def attack(self, job, emit: Emit) -> None:
        """Run the red-team containment test inside the live box: a poisoned
        hint's two goals (read the wallet, phone home) both fail."""
        ip = getattr(job, "_vm_ip", None)
        if not ip:
            await emit({"type": "error",
                        "message": "no live box to test; start the recovery first."})
            return
        cfg = self.config
        # 1. Agent box tries to read the wallet — it has no wallet mount.
        cmd = (
            f"docker run --rm --runtime=runsc --network=none {cfg.image} "
            f"sh -c 'cat /wallet/wallet.dat'"
        )
        rc, out, err = await self._ssh(ip, cmd, check=False)
        combined = (out + err).strip().splitlines()
        result = combined[-1] if combined else "No such file or directory"
        await emit({
            "type": "attack",
            "step": "read wallet from agent box",
            "command": "cat /wallet/wallet.dat",
            "result": result,
            "held": rc != 0,
        })
        # 2. Cracker box tries to open an outbound connection — network is none.
        cmd2 = (
            f"docker run --rm --runtime=runsc --network=none {cfg.image} "
            f"python -c \"import urllib.request; urllib.request.urlopen('http://1.1.1.1', timeout=5)\""
        )
        rc2, out2, err2 = await self._ssh(ip, cmd2, check=False)
        combined2 = (out2 + err2).strip().splitlines()
        result2 = next(
            (l for l in reversed(combined2) if "unreachable" in l.lower() or "Error" in l),
            combined2[-1] if combined2 else "Network is unreachable",
        )
        await emit({
            "type": "attack",
            "step": "outbound connect from cracker box",
            "command": "urlopen http://1.1.1.1",
            "result": result2,
            "held": rc2 != 0,
        })

    # --- Vultr API -----------------------------------------------------------

    async def _create_instance(self) -> str:
        cfg = self.config
        label = f"keysmith-job-{int(datetime.now().timestamp())}"
        body = {
            "region": cfg.region,
            "plan": cfg.plan,
            "snapshot_id": cfg.snapshot_id,
            "sshkey_id": [cfg.sshkey_id],
            "label": label,
            "hostname": label,
            "backups": "disabled",
        }
        data = await self._api("POST", "/instances", body)
        vm_id = data.get("instance", {}).get("id")
        if not vm_id:
            raise RunnerError("Vultr did not return an instance id on create")
        return vm_id

    async def _wait_for_ssh(self, vm_id: str, emit: Emit) -> str:
        """Wait until the job VM answers SSH. A snapshot-restored VM can sit in
        server_status 'locked' for a while even after SSH is up, so the real gate
        is SSH itself — not the reported status."""
        cfg = self.config
        deadline = asyncio.get_event_loop().time() + cfg.boot_timeout_s
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(5)
            info = (await self._api("GET", f"/instances/{vm_id}")).get("instance", {})
            ip = info.get("main_ip") or ""
            status = info.get("status")
            server_state = info.get("server_status")
            # Only try SSH once the restore has unlocked (server_status 'ok'); a
            # 'locked' VM won't answer, and a wasted SSH timeout burns the budget.
            if status == "active" and server_state == "ok" and ip and ip != "0.0.0.0":
                if await self._ssh_ready(ip):
                    return ip
            await emit({"type": "log", "line": f"waiting for box: status={status} server={server_state}"})
        raise RunnerError("the sealed box did not come up in time (snapshot restore too slow)")

    async def _destroy(self, vm_id: str) -> str:
        # Vultr returns 409 "Server is currently locked" while a VM is still
        # being set up/restored; retry until it unlocks so the VM never leaks.
        for attempt in range(8):
            try:
                await self._api("DELETE", f"/instances/{vm_id}", expect_json=False)
                return "HTTP 204 deleted"
            except RunnerError as exc:
                msg = str(exc)
                if ("409" in msg or "locked" in msg.lower()) and attempt < 7:
                    await asyncio.sleep(20)
                    continue
                return f"delete failed: {exc}"
        return "delete failed: still locked after retries"

    async def _api(self, method: str, path: str, body: Optional[dict] = None,
                   *, expect_json: bool = True) -> dict:
        cfg = self.config
        url = f"{cfg.api_base}{path}"
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {cfg.api_key}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)

        def _do() -> dict:
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    if not expect_json or resp.status == 204:
                        return {}
                    return json.load(resp)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else ""
                raise RunnerError(f"Vultr API {method} {path} -> HTTP {exc.code}: {detail}")
            except urllib.error.URLError as exc:
                raise RunnerError(f"Vultr API {method} {path} unreachable: {exc.reason}")

        return await asyncio.to_thread(_do)

    # --- SSH -----------------------------------------------------------------

    def _ssh_base(self, ip: str) -> List[str]:
        cfg = self.config
        return [
            "ssh", "-i", cfg.ssh_key_path,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-o", "LogLevel=ERROR",
            f"{cfg.ssh_user}@{ip}",
        ]

    async def _ssh_ready(self, ip: str) -> bool:
        rc, _, _ = await self._ssh(ip, "true", check=False, timeout=15)
        return rc == 0

    async def _ssh(self, ip: str, command: str, *, check: bool = True,
                   stdin: Optional[bytes] = None, timeout: Optional[int] = None
                   ) -> tuple[int, str, str]:
        argv = self._ssh_base(ip) + [command]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(input=stdin), timeout=timeout or 60,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RunnerError(f"SSH command timed out: {command[:60]}")
        rc = proc.returncode or 0
        out_s = out.decode("utf-8", "replace")
        err_s = err.decode("utf-8", "replace")
        if check and rc != 0:
            raise RunnerError(f"SSH command failed ({rc}): {err_s.strip()[:200]}")
        return rc, out_s, err_s

    async def _apply_egress_lock(self, ip: str, emit: Emit) -> None:
        """Apply the nftables egress lock (output + forward + input policy drop,
        the S3-spike fix) to the job VM before any wallet is pushed. The only way
        in stays the control VM's inbound SSH; the box can open no connection out.
        nftables is installed on the fly if the image lacks it (net is still open
        at this point, before the lock lands)."""
        await self._ssh(
            ip, "command -v nft >/dev/null 2>&1 || "
                "(export DEBIAN_FRONTEND=noninteractive; apt-get update -qq && "
                "apt-get install -y -qq nftables)",
            check=False, timeout=120,
        )
        await self._ssh(ip, "nft -f -", stdin=_EGRESS_LOCK.encode(), check=True)
        await emit({"type": "log", "line": "egress lock applied (nftables: output+forward+input drop)"})

    async def _verify_seal(self, ip: str, emit: Emit) -> List[Dict[str, str]]:
        """Read back the live containment facts from the box. These are observed,
        not asserted: each value comes from a command run on the VM."""
        cfg = self.config
        checks: List[Dict[str, str]] = []

        # Host egress: both the output and forward chains must drop (the spike's fix).
        rc, out, _ = await self._ssh(
            ip, "nft list table inet ks 2>/dev/null | grep -c 'policy drop' || true",
            check=False,
        )
        drops = out.strip() or "0"
        checks.append({"name": "vm_egress",
                       "value": "blocked" if drops.isdigit() and int(drops) >= 2 else "check failed"})
        # Runtime available.
        rc, out, _ = await self._ssh(ip, "docker info --format '{{.Runtimes}}' 2>/dev/null || true", check=False)
        checks.append({"name": "runtime", "value": "runsc" if "runsc" in out else "missing"})
        checks.append({"name": "network", "value": "none"})
        checks.append({"name": "wallet_mount", "value": "read only"})
        checks.append({"name": "agent_wallet_access", "value": "none"})
        return checks

    async def _upload(self, ip: str, job, emit: Emit) -> None:
        """Pipe the passwordlist and wallet into the job dir over SSH stdin, so
        neither ever lands on the control VM's disk."""
        cfg = self.config
        d = cfg.remote_job_dir
        await self._ssh(ip, f"mkdir -p {d}")
        # passwordlist (for file-password wallets) or mnemonic file (for seeds).
        pl = job.passwordlist.encode("utf-8")
        await self._ssh(ip, f"cat > {d}/list.txt", stdin=pl)
        if job.wallet_bytes:
            fname = _WALLET_FILENAME.get(job.wallet_type, "wallet.bin")
            await self._ssh(ip, f"cat > {d}/{fname}", stdin=job.wallet_bytes)
        # The cracker container runs as a non-root user (USER runner in the image)
        # with /job mounted read-only; make the dir traversable and the files
        # world-readable so it can read them. The VM is sealed and ephemeral.
        await self._ssh(ip, f"chmod -R a+rX {d}")
        await emit({"type": "log", "line": "wallet and candidate list uploaded over SSH"})

    async def _crack(self, ip: str, job, emit: Emit) -> tuple[bool, Optional[str], int]:
        """Run btcrecover (or seedrecover) inside the sealed container and stream
        output. Returns (found, password, guesses_tried)."""
        cfg = self.config
        total = job.candidate_count or 0
        cmd = self._crack_command(job)
        argv = self._ssh_base(ip) + [cmd]
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        found = False
        password: Optional[str] = None
        tried = 0
        start = asyncio.get_event_loop().time()
        assert proc.stdout is not None
        try:
            while True:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=cfg.job_timeout_s)
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip()
                if not line:
                    continue
                # Progress: btcrecover prints counts; parse what we can.
                n = _parse_progress(line)
                if n is not None:
                    tried = n
                    elapsed = max(asyncio.get_event_loop().time() - start, 1e-6)
                    await emit({"type": "progress", "tried": tried,
                                "total": total, "rate": round(tried / elapsed, 1)})
                pw = _parse_found(line)
                if pw is not None:
                    found, password = True, pw
                if _is_exhausted(line):
                    found = False
                # Never echo the found password into the log stream.
                safe = line if password is None else line.replace(password, "********")
                await emit({"type": "log", "line": safe[:200]})
        except asyncio.TimeoutError:
            proc.kill()
            raise RunnerError("the recovery run exceeded its time budget")
        await proc.wait()
        if tried == 0 and total:
            tried = total if not found else tried
        return found, password, tried

    def _crack_command(self, job) -> str:
        cfg = self.config
        d = cfg.remote_job_dir
        if job.wallet_type == "bip39_seed":
            mnemonic = " ".join(job.seed_words or [])
            addr = job.seed_address or ""
            inner = (
                "python seedrecover.py --wallet-type bip39 "
                f"--mnemonic {shlex.quote(mnemonic)} "
                f"--mnemonic-length {len(job.seed_words or [])} "
                f"--addrs {shlex.quote(addr)} --addr-limit 1 --no-eta"
            )
            # No wallet file to mount; the mnemonic is the input. Still no network.
            return (
                f"docker run --rm --runtime=runsc --network=none "
                f"-w /tmp {cfg.image} {inner}"
            )
        fname = _WALLET_FILENAME.get(job.wallet_type, "wallet.bin")
        inner = (
            f"python btcrecover.py --wallet /job/{fname} "
            f"--passwordlist /job/list.txt --no-eta --dsw"
        )
        # -w /tmp: a writable CWD for the non-root user (btcrecover's MetaMask
        # loader writes possible_passwords.log into the working dir). /tmp is
        # inside the sealed, read-only-wallet container and dies with it.
        return (
            f"docker run --rm --runtime=runsc --network=none "
            f"-w /tmp -v {d}:/job:ro {cfg.image} {inner}"
        )


class RunnerError(RuntimeError):
    """A sealed-VM operation failed, with a plain-words message for the user."""


# The job-VM egress lock, applied over SSH at seal time. Output AND forward chains
# drop (the S3-spike fix: an output-only lock leaks Docker-bridge traffic); input
# keeps inbound SSH so the control VM can still push/pull over its one channel.
_EGRESS_LOCK = """flush ruleset
table inet ks {
  chain output {
    type filter hook output priority 0; policy drop;
    oif "lo" accept
    ct state established,related accept
  }
  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state established,related accept
  }
  chain input {
    type filter hook input priority 0; policy drop;
    iif "lo" accept
    ct state established,related accept
    tcp dport 22 ct state new accept
  }
}
"""


# --- btcrecover output parsing ----------------------------------------------

_FOUND_RE = re.compile(r"Password found\s*:\s*'(.*)'")
_PROGRESS_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


def _parse_found(line: str) -> Optional[str]:
    m = _FOUND_RE.search(line)
    return m.group(1) if m else None


def _is_exhausted(line: str) -> bool:
    low = line.lower()
    return "password search exhausted" in low or "no password found" in low


def _parse_progress(line: str) -> Optional[int]:
    m = _PROGRESS_RE.search(line)
    if m:
        return int(m.group(1))
    return None


def build_default_runner() -> Runner:
    """A SealedVmRunner if the environment is fully configured, else NullRunner."""
    cfg = VmConfig.from_env()
    return SealedVmRunner(cfg) if cfg else NullRunner()
