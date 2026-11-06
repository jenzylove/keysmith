# btcrecover image, baked into the job-VM snapshot.
#
# The image runs with `--runtime=runsc --network=none` and the wallet mounted
# read-only. It carries no credentials and never has network at runtime.
#
# btcrecover (gurnec/btcrecover) is a long-standing open-source wallet-recovery
# tool. We pin a commit at build time (BTCRECOVER_REF) for reproducibility.
FROM python:3.12-slim

ARG BTCRECOVER_REF=master

RUN apt-get update \
 && apt-get install -y --no-install-recommends git build-essential libssl-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone https://github.com/gurnec/btcrecover.git \
 && cd btcrecover \
 && git checkout "${BTCRECOVER_REF}"

WORKDIR /opt/btcrecover
# btcrecover's own requirements plus the extras its wallet modules need.
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir coincurve pycryptodome protobuf

# A non-root user; the wallet is mounted read-only regardless.
RUN useradd -m -u 10001 runner
USER runner

# No ENTRYPOINT: the control VM passes the exact command
# (`python btcrecover.py --wallet /job/<file> --passwordlist /job/list.txt ...`
#  or `python seedrecover.py ...`) at `docker run` time.
WORKDIR /opt/btcrecover
