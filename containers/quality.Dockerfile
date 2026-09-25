ARG DEBIAN_VERSION=13
ARG RUSTUP_INIT_VERSION=1.28.2
ARG RUST_STABLE=1.85.0
ARG RUST_NIGHTLY=nightly-2025-02-20
FROM ghcr.io/cpeter1207/usbradioplus-quality-debian${DEBIAN_VERSION}:latest
ARG TARGETARCH
ARG RUSTUP_INIT_VERSION
ARG RUST_STABLE
ARG RUST_NIGHTLY
ARG CARGO_LLVM_COV_VERSION=0.6.21
LABEL org.opencontainers.image.source="https://github.com/cpeter1207/rpt_advanced-workflows"
LABEL org.opencontainers.image.description="rpt_advanced ASL3 quality test environment"
ENV RUSTUP_HOME=/opt/rustup
ENV CARGO_HOME=/opt/cargo
ENV PATH="/opt/cargo/bin:/opt/usbradioplus-quality/bin:${PATH}"
COPY --from=dependencies . /tmp/dependencies/
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      curl ffmpeg libclang-dev /tmp/dependencies/*.deb && \
    rm -rf /var/lib/apt/lists/* /tmp/dependencies
RUN case "${TARGETARCH}" in \
      amd64) rustup_host=x86_64-unknown-linux-gnu; rustup_sha=20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c ;; \
      arm64) rustup_host=aarch64-unknown-linux-gnu; rustup_sha=e3853c5a252fca15252d07cb23a1bdd9377a8c6f3efa01531109281ae47f841c ;; \
      *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
      "https://static.rust-lang.org/rustup/archive/${RUSTUP_INIT_VERSION}/${rustup_host}/rustup-init" \
      --output /tmp/rustup-init; \
    printf '%s  %s\n' "${rustup_sha}" /tmp/rustup-init > /tmp/rustup-init.sha256; \
    sha256sum --check --status /tmp/rustup-init.sha256; \
    chmod 0755 /tmp/rustup-init; \
    /tmp/rustup-init -y --no-modify-path --default-toolchain none; \
    rm -f /tmp/rustup-init /tmp/rustup-init.sha256; \
    rustup toolchain install "${RUST_STABLE}" --profile minimal --component clippy --component rustfmt; \
    rustup toolchain install "${RUST_NIGHTLY}" --profile minimal --component llvm-tools-preview; \
    rustup default "${RUST_STABLE}"; \
    cargo +"${RUST_NIGHTLY}" install cargo-llvm-cov --version "${CARGO_LLVM_COV_VERSION}" --locked; \
    rustc_version="$(rustc --version)"; case "$rustc_version" in *"${RUST_STABLE}"*) ;; *) exit 1 ;; esac; \
    rustfmt --version; \
    coverage_version="$(cargo +"${RUST_NIGHTLY}" llvm-cov --version)"; case "$coverage_version" in *"${CARGO_LLVM_COV_VERSION}"*) ;; *) exit 1 ;; esac
WORKDIR /work
