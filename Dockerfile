# Production image for the streamable-http (multi-tenant) mode only —
# this is what runs as mcp.iotamine.com. stdio mode (what
# `uvx iotamine-mcp` runs on someone's own machine) has no business in
# a container: it's a local process talking to a local MCP client over
# stdin/stdout.
#
# Two stages so the final image doesn't carry build-essential or the
# MySQL/etc headers other services in this repo need but this one
# doesn't — this package's only real dependencies are mcp + httpx
# (pure Python; nothing here needs compiling, but pip occasionally
# still wants a compiler present for a transitive dep's sdist, so the
# builder stage has one and the final stage doesn't).

FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir --upgrade pip

# Copy only what the build needs first, so `pip install .` is cached
# across rebuilds that only touch tests/README/etc.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --prefix=/install .


FROM python:3.12-slim

# ca-certificates: httpx talks HTTPS to the real Iotamine API
# (iotamine.com) and to the OAuth issuer for token verification.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN useradd --create-home --shell /usr/sbin/nologin --uid 1000 iotamine
USER iotamine
WORKDIR /home/iotamine

# Required at runtime (no defaults — a missing value should fail
# loudly at startup, not silently serve with the wrong issuer/resource
# advertised to clients):
#   IOTAMINE_OAUTH_ISSUER_URL   e.g. https://iotamine.com
#   IOTAMINE_MCP_RESOURCE_URL   e.g. https://mcp.iotamine.com/mcp
# Optional:
#   IOTAMINE_API_URL            defaults to https://iotamine.com/api/
ENV IOTAMINE_MCP_TRANSPORT=streamable-http \
    IOTAMINE_MCP_HOST=0.0.0.0 \
    IOTAMINE_MCP_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"

CMD ["iotamine-mcp"]
