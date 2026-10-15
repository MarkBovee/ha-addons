ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

# Upstream npm release to install. Bump together with the add-on version.
ARG MS365_MCP_VERSION=0.158.0

# nodejs >= 20 is required by the MCP server (Alpine ships a newer LTS), nginx
# fronts it with the bearer-token check, curl is used by the health check.
# --ignore-scripts mirrors upstream's own image: the optional native "keytar"
# module cannot build on musl, and the add-on stores tokens in /data instead.
RUN apk add --no-cache nodejs npm nginx curl jq \
    && node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)" \
    && npm install -g --ignore-scripts "@softeria/ms-365-mcp-server@${MS365_MCP_VERSION}" \
    && npm cache clean --force \
    && ms-365-mcp-server --version

COPY run.sh /
RUN chmod a+x /run.sh

# The start period covers the wait for the one-time device-code login (up to ~16 min).
HEALTHCHECK --interval=60s --timeout=5s --start-period=1000s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/healthz >/dev/null || exit 1

CMD [ "/run.sh" ]
