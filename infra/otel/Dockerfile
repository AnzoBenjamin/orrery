# OpenTelemetry Collector (contrib) with curl for the health check. The upstream image is built
# from scratch and has no shell or HTTP client.
FROM otel/opentelemetry-collector-contrib:0.165.0@sha256:e40d61f10c9a617cca1ffd1be4d7e2b3a4b0f0001798ff07e58cabe82e618cea AS otelcol

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
COPY --from=otelcol /otelcol-contrib /usr/local/bin/otelcol-contrib
COPY config.yaml /etc/otelcol/config.yaml
USER 10001:10001
ENTRYPOINT ["otelcol-contrib"]
CMD ["--config", "/etc/otelcol/config.yaml"]
