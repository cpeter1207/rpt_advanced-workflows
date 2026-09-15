ARG DEBIAN_VERSION=13
FROM ghcr.io/cpeter1207/usbradioplus-quality-debian${DEBIAN_VERSION}:latest
ARG CARGO_LLVM_COV_VERSION=0.6.21
LABEL org.opencontainers.image.source="https://github.com/cpeter1207/rpt_advanced-workflows"
LABEL org.opencontainers.image.description="rpt_advanced ASL3 quality test environment"
ENV PATH="/opt/usbradioplus-quality/bin:${PATH}"
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*
RUN cargo install cargo-llvm-cov --version "${CARGO_LLVM_COV_VERSION}" --locked && \
    cargo llvm-cov --version
WORKDIR /work
