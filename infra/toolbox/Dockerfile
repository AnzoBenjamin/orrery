# syntax=docker/dockerfile:1.12
#
# Orrery toolbox: every toolchain the repository needs, pinned. Developers, agents, and CI run all
# project commands in this image (see .kiro/steering/structure.md, "Docker-first rule").
#
# Pins: Node.js and Debian come from the digest-pinned base image. FFmpeg and system libraries are the
# Debian trixie packages in that image's snapshot. Everything else is pinned by version and checksum.

FROM node:26.13.1-trixie-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc

ARG TARGETARCH
ARG UID=1000
ARG GID=1000

ARG PNPM_VERSION=12.18.0
ARG UV_VERSION=0.13.8
ARG PYTHON_VERSION=3.13.18
ARG RUSTUP_VERSION=1.29.2
ARG RUST_VERSION=1.100.0
ARG WASM_PACK_VERSION=0.15.1
ARG PLAYWRIGHT_VERSION=1.65.0
ARG OSV_SCANNER_VERSION=2.7.1
ARG CARGO_TYPIFY_VERSION=0.8.0
ARG WASM_BINDGEN_VERSION=0.2.130

ENV DEBIAN_FRONTEND=noninteractive \
    RUSTUP_HOME=/opt/rustup \
    CARGO_HOME=/opt/cargo \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/workspace/.venv \
    PYO3_PYTHON=/opt/uv-python/python3 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    TURBO_TELEMETRY_DISABLED=1 \
    PATH=/opt/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# System packages. The X11 and GL libraries are the runtime dependencies of the `bpy` (Blender as a
# Python module) wheel used by tools/lab for CPU Cycles rendering.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash ca-certificates curl git make procps xz-utils \
      build-essential pkg-config libssl-dev \
      ffmpeg \
      libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libgl1 libegl1 libsm6 libice6 \
 && rm -rf /var/lib/apt/lists/*

# Host-matched user, so files written to the bind-mounted workspace belong to the developer.
# The base image ships a `node` user at UID 1000, which would collide with the common host UID.
RUN userdel --remove node 2>/dev/null || true \
 && (getent group "${GID}" >/dev/null || groupadd --gid "${GID}" dev) \
 && useradd --create-home --uid "${UID}" --gid "${GID}" --shell /bin/bash dev

# uv
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) triple=x86_64-unknown-linux-gnu; sum=5acfd9177cfecf0bf87578f059728215ccc884388988f55f7a65041b57387d91 ;; \
      arm64) triple=aarch64-unknown-linux-gnu; sum=74f2f5c6024d397481db228db8fc25eed420db192243f88438c118e7e013e585 ;; \
      *) echo "unsupported arch ${TARGETARCH}"; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${triple}.tar.gz" -o /tmp/uv.tgz; \
    echo "${sum}  /tmp/uv.tgz" | sha256sum -c -; \
    tar -xzf /tmp/uv.tgz -C /usr/local/bin --strip-components=1; \
    rm /tmp/uv.tgz; \
    UV_PYTHON_DOWNLOADS=automatic uv python install "${PYTHON_VERSION}"; \
    # PYO3_PYTHON: the interpreter crates/kinematics-py builds against.
    ln -s "$(uv python find --no-project "${PYTHON_VERSION}")" /opt/uv-python/python3

# Rust
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) triple=x86_64-unknown-linux-gnu; sum=5be191e8c70a5007074254cb74d78dbfdd25cd5a61c27de7b8e5410122ec24f4 ;; \
      arm64) triple=aarch64-unknown-linux-gnu; sum=a9c168dbea81a84671c6b7a5c1795cb0eb699020110d107ddfca427bd797e697 ;; \
    esac; \
    curl -fsSL "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/${triple}/rustup-init" -o /tmp/rustup-init; \
    echo "${sum}  /tmp/rustup-init" | sha256sum -c -; \
    chmod +x /tmp/rustup-init; \
    /tmp/rustup-init -y --no-modify-path --profile minimal --default-toolchain "${RUST_VERSION}" \
      --component rustfmt --component clippy --target wasm32-unknown-unknown; \
    rm /tmp/rustup-init

# cargo-typify: Rust types from the mechanism JSON Schema (structure.md, "Contracts flow one way").
# wasm-bindgen-cli: the version must equal the wasm-bindgen crate in Cargo.lock; wasm-pack uses it
# instead of downloading one at build time.
# Built from crates.io with its own lockfile; the registry cache is dropped from the layer.
RUN cargo install --locked --root /usr/local "cargo-typify@${CARGO_TYPIFY_VERSION}" \
 && cargo install --locked --root /usr/local "wasm-bindgen-cli@${WASM_BINDGEN_VERSION}" \
 && rm -rf /opt/cargo/registry /opt/cargo/git

# wasm-pack
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) triple=x86_64-unknown-linux-musl; sum=410101009739b9d01c7d5affaaad6e9c9a24b4cba6791a4805db8e89b9bf7af2 ;; \
      arm64) triple=aarch64-unknown-linux-musl; sum=7004853c7925ae1984033b5f25866ec604bbc921ef956d5e6c5595bc5af6d30c ;; \
    esac; \
    curl -fsSL "https://github.com/wasm-bindgen/wasm-pack/releases/download/v${WASM_PACK_VERSION}/wasm-pack-v${WASM_PACK_VERSION}-${triple}.tar.gz" -o /tmp/wasm-pack.tgz; \
    echo "${sum}  /tmp/wasm-pack.tgz" | sha256sum -c -; \
    tar -xzf /tmp/wasm-pack.tgz -C /usr/local/bin --strip-components=1 --wildcards '*/wasm-pack'; \
    rm /tmp/wasm-pack.tgz

# OSV-Scanner (Apache-2.0): dependency vulnerability scanning of pnpm, uv, and Cargo lockfiles
# (requirement 12.5, scripts/scan-dependencies.ts).
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) sum=fb7dab19a8bd9bbe5c3189f09d4b7ee1820c9553a23bac202648a56efd2f6ee8 ;; \
      arm64) sum=983d22fbad9724514e3fcc6acc83b5fa64c5ffa6b0d9f510028f22c1b223ff81 ;; \
    esac; \
    curl -fsSL "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_linux_${TARGETARCH}" -o /usr/local/bin/osv-scanner; \
    echo "${sum}  /usr/local/bin/osv-scanner" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/osv-scanner

# pnpm (Node.js 25 and later no longer bundle Corepack) and Playwright's Chromium with its system deps.
RUN npm install --global "pnpm@${PNPM_VERSION}" \
 && npx --yes "playwright@${PLAYWRIGHT_VERSION}" install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* /root/.npm

# Cache directories are mounted as named volumes. Creating them here makes the volumes inherit
# the dev user's ownership on first use.
RUN mkdir -p /workspace /home/dev/.cache/uv /home/dev/.local/share/pnpm /opt/cargo/registry /opt/cargo/git \
 && chown -R "${UID}:${GID}" /workspace /home/dev /opt/cargo /opt/rustup /opt/uv-python

USER dev
WORKDIR /workspace
ENV PNPM_HOME=/home/dev/.local/share/pnpm \
    npm_config_store_dir=/home/dev/.local/share/pnpm/store

CMD ["bash"]
