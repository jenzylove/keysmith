#!/usr/bin/env bash
# Build the Keysmith job-VM snapshot via the Vultr API.
#
# Needs VULTR_API_KEY in the environment. Two subcommands:
#
#   build-snapshot.sh provision <vm_ip> [ssh_key]
#       Copy the snapshot/ files to an existing builder VM and run provision.sh
#       on it (installs Docker + gVisor + btcrecover image).
#
#   build-snapshot.sh snapshot <vm_id> [description]
#       Take a Vultr snapshot of that (now-provisioned) VM, poll until complete,
#       and print the snapshot id to set as KEYSMITH_SNAPSHOT_ID.
#
# Keep the builder VM OFF between hackathon sessions (or delete it) to save money;
# the control VM only needs the snapshot id, not the builder.
set -euo pipefail

API="https://api.vultr.com/v2"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${VULTR_API_KEY:?set VULTR_API_KEY}"

auth=(-H "Authorization: Bearer ${VULTR_API_KEY}")

case "${1:-}" in
  provision)
    ip="${2:?usage: provision <vm_ip> [ssh_key]}"
    key="${3:-$HOME/keysmith-launch/ssh/id_ed25519}"
    scp -i "$key" -o StrictHostKeyChecking=no \
      "$HERE/Dockerfile" "$HERE/provision.sh" "root@${ip}:/root/snapshot/" 2>/dev/null \
      || { ssh -i "$key" -o StrictHostKeyChecking=no "root@${ip}" "mkdir -p /root/snapshot"; \
           scp -i "$key" -o StrictHostKeyChecking=no "$HERE/Dockerfile" "$HERE/provision.sh" "root@${ip}:/root/snapshot/"; }
    ssh -i "$key" -o StrictHostKeyChecking=no "root@${ip}" \
      "chmod +x /root/snapshot/provision.sh && /root/snapshot/provision.sh"
    echo "Provisioned ${ip}. Next: $0 snapshot <vm_id>"
    ;;

  snapshot)
    vm_id="${2:?usage: snapshot <vm_id> [description]}"
    desc="${3:-keysmith job vm (docker+gVisor+btcrecover)}"
    echo "Creating snapshot of ${vm_id}…"
    resp="$(curl -s "${auth[@]}" -H "Content-Type: application/json" \
      -X POST "${API}/snapshots" \
      -d "{\"instance_id\":\"${vm_id}\",\"description\":\"${desc}\"}")"
    snap_id="$(printf '%s' "$resp" | python3 -c 'import sys,json;print(json.load(sys.stdin)["snapshot"]["id"])')"
    echo "snapshot id: ${snap_id}"
    echo -n "waiting for complete"
    while :; do
      sleep 10; echo -n "."
      status="$(curl -s "${auth[@]}" "${API}/snapshots/${snap_id}" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["snapshot"]["status"])')"
      [ "$status" = "complete" ] && break
    done
    echo
    echo "DONE. Set: export KEYSMITH_SNAPSHOT_ID=${snap_id}"
    ;;

  *)
    echo "usage: $0 {provision <vm_ip> [ssh_key] | snapshot <vm_id> [description]}" >&2
    exit 2
    ;;
esac
