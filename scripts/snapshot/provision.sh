#!/usr/bin/env bash
# Provision a builder VM so it can be snapshotted into the Keysmith job-VM image.
# Installs Docker + gVisor (runsc), makes runsc a Docker runtime, and builds the
# btcrecover image. Run this ON the builder VM (as root), then snapshot it.
#
# Timings from the S3 spike: Docker ~40 s, gVisor ~20 s. Baking the image in
# means job VMs need zero install time at boot — just the egress lock.
set -euo pipefail

BTCRECOVER_REF="${BTCRECOVER_REF:-master}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/4] Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

echo "[2/4] gVisor (runsc)"
if ! command -v runsc >/dev/null 2>&1; then
  (
    set -e
    ARCH="$(uname -m)"
    URL="https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}"
    wget -q "${URL}/runsc" "${URL}/runsc.sha512" \
         "${URL}/containerd-shim-runsc-v1" "${URL}/containerd-shim-runsc-v1.sha512"
    sha512sum -c runsc.sha512 -c containerd-shim-runsc-v1.sha512
    chmod a+rx runsc containerd-shim-runsc-v1
    mv runsc containerd-shim-runsc-v1 /usr/local/bin/
  )
  /usr/local/bin/runsc install
fi

echo "[3/4] Docker daemon: register runsc runtime"
install -d /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "runtimes": { "runsc": { "path": "/usr/local/bin/runsc" } }
}
JSON
systemctl restart docker

echo "[4/4] Build btcrecover image (ref ${BTCRECOVER_REF})"
docker build --build-arg "BTCRECOVER_REF=${BTCRECOVER_REF}" \
  -t keysmith/btcrecover "${HERE}"

echo "Sanity: runsc + image present, no network at runtime"
docker run --rm --runtime=runsc --network=none keysmith/btcrecover \
  python -c "print('btcrecover image OK, network none')"

echo "Provisioned. Now snapshot this VM (scripts/snapshot/build-snapshot.sh snapshot <vm_id>)."
