# The sandbox image for Remedy Atlas: the project's checks and any study that
# needs native packages run in it, rootless, with no network and a read-only
# root filesystem (see docs/sandbox.md). `python3 research/env.py setup`
# builds it; the tag is a hash of this directory, so a reviewed change here
# rebuilds it. Changing this file needs a maintainer.
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

# The checks use git (research/atlas.py check) and node (the site tests).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git nodejs \
 && rm -rf /var/lib/apt/lists/*

# Hash-locked research tiers. Add bayes or gpu here when a track needs them
# (gpu adds several GB on Linux). libRoadRunner (qsp) publishes Linux wheels
# for x86-64 only, so ARM images (Apple silicon, Graviton) leave it out.
ARG TARGETARCH
COPY constraints.txt requirements-core.txt requirements-fast.txt requirements-chem.txt requirements-qsp.txt /tmp/req/
RUN python -m pip install --no-cache-dir --no-input --require-hashes \
      -r /tmp/req/requirements-core.txt -r /tmp/req/requirements-fast.txt -r /tmp/req/requirements-chem.txt \
 && if [ "$TARGETARCH" = "amd64" ]; then \
      python -m pip install --no-cache-dir --no-input --require-hashes -r /tmp/req/requirements-qsp.txt; fi \
 && rm -rf /tmp/req

USER 65534:65534
WORKDIR /work
