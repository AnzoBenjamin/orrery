# Garage with a shell, curl, and jq. The upstream image contains only the static binary, which leaves
# no way to run a health check or the bucket bootstrap (bootstrap.sh) inside the container.
FROM dxflrs/garage:v2.5.0@sha256:677e5b758e4425a325b811c425c026bf35a4bf42f7ddbaa773de3f4fd779a5a5 AS garage

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl jq \
 && rm -rf /var/lib/apt/lists/*
COPY --from=garage /garage /usr/local/bin/garage
RUN useradd --system --uid 10001 --home-dir /var/lib/garage garage \
 && mkdir -p /var/lib/garage/meta /var/lib/garage/data \
 && chown -R garage /var/lib/garage
COPY garage.toml /etc/garage.toml
COPY bootstrap.sh /usr/local/bin/garage-bootstrap
USER garage
ENTRYPOINT ["garage"]
CMD ["server"]
