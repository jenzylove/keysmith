"""Teardown receipt: the proof shown after a job ends.

The product's trust claim is "the wallet never leaves the box and the box is
destroyed." The receipt is how we show that: the sealed VM/container identity,
when it was created and destroyed, how many bytes left it (must be 0 for the
wallet), and the Vultr API delete result. Pure data + serialization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional

# Isolation mode actually used for the job (shown on the run page honestly).
MODE_PER_JOB_VM = "per_job_vm"          # fresh Vultr VM created + destroyed
MODE_RUNNER_CONTAINER = "runner_container"  # gVisor container on a runner VM

OUTCOME_FOUND = "found"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_ERROR = "error"

_MODES = {MODE_PER_JOB_VM, MODE_RUNNER_CONTAINER}
_OUTCOMES = {OUTCOME_FOUND, OUTCOME_NOT_FOUND, OUTCOME_TIMEOUT, OUTCOME_ERROR}


class ReceiptError(ValueError):
    pass


@dataclass
class TeardownReceipt:
    job_id: str
    mode: str
    wallet_type: str
    outcome: str
    created_at: str              # ISO 8601 UTC
    destroyed_at: str            # ISO 8601 UTC
    guesses_tried: int
    bytes_egressed_wallet: int   # bytes of wallet data that left the box; must be 0
    vm_id: Optional[str] = None  # Vultr instance id, when mode is per_job_vm
    api_delete_status: Optional[str] = None  # Vultr API delete response summary
    network_mode: str = "none"   # container network mode on the cracker
    agent_wallet_mounts: int = 0 # wallet mounts visible to the agent; must be 0

    def validate(self) -> "TeardownReceipt":
        if self.mode not in _MODES:
            raise ReceiptError(f"mode must be one of {_MODES}")
        if self.outcome not in _OUTCOMES:
            raise ReceiptError(f"outcome must be one of {_OUTCOMES}")
        if self.guesses_tried < 0:
            raise ReceiptError("guesses_tried must be >= 0")
        if self.bytes_egressed_wallet < 0:
            raise ReceiptError("bytes_egressed_wallet must be >= 0")
        if self.mode == MODE_PER_JOB_VM and not self.vm_id:
            raise ReceiptError("per_job_vm receipts must carry a vm_id")
        return self

    def containment_held(self) -> bool:
        """True iff the containment invariants held for this job: no wallet bytes
        left the box, the cracker had no network, and the agent could not see the
        wallet."""
        return (
            self.bytes_egressed_wallet == 0
            and self.network_mode == "none"
            and self.agent_wallet_mounts == 0
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["containment_held"] = self.containment_held()
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)
