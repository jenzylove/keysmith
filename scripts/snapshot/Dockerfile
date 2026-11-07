# btcrecover image, baked into the job-VM snapshot.
#
# The image runs with `--runtime=runsc --network=none` and the wallet mounted
# read-only. It carries no credentials and never has network at runtime.
#
# btcrecover is a long-standing open-source wallet-recovery tool. We use the
# actively maintained 3rdIteration fork (the original gurnec repo stopped at a
# 2017 commit with no requirements.txt and no MetaMask support). We pin a commit
# at build time (BTCRECOVER_REF) for reproducibility.
FROM python:3.12-slim

# Pinned 3rdIteration/btcrecover commit (2026-07-17). Override to track master.
ARG BTCRECOVER_REF=1457088

RUN apt-get update \
 && apt-get install -y --no-install-recommends git build-essential libssl-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone https://github.com/3rdIteration/btcrecover.git \
 && cd btcrecover \
 && git checkout "${BTCRECOVER_REF}"

WORKDIR /opt/btcrecover
# requirements.txt already pins coincurve, pycryptodome and protobuf — the libs
# the MetaMask / Ethereum / BIP39 wallet modules need.
RUN pip install --no-cache-dir -r requirements.txt

# A non-root user; the wallet is mounted read-only regardless.
RUN useradd -m -u 10001 runner
USER runner

# No ENTRYPOINT: the control VM passes the exact command
# (`python btcrecover.py --wallet /job/<file> --passwordlist /job/list.txt ...`
#  or `python seedrecover.py ...`) at `docker run` time.
WORKDIR /opt/btcrecover
