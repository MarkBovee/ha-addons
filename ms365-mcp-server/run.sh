#!/usr/bin/with-contenv bashio
# shellcheck shell=bash

# Layout inside the container:
#   LAN :3000  -> nginx (bearer-token check, only /mcp and /healthz)
#   127.0.0.1:3001 -> ms-365-mcp-server --http --trust-proxy-auth
# --trust-proxy-auth makes the MCP server skip its own Bearer check and use the
# MSAL identity cached in /data, so nginx MUST stay in front of it.

readonly PROXY_PORT=3000
readonly NODE_PORT=3001
readonly NGINX_CONF=/etc/nginx/ms365-mcp.conf

bashio::log.info "Starting Microsoft 365 MCP Server add-on..."

# ---------------------------------------------------------------- options
client_id=$(bashio::config 'client_id')
tenant_id=$(bashio::config 'tenant_id' 'consumers')
access_token=$(bashio::config 'access_token')

if [[ ! "${client_id}" =~ ^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$ ]]; then
    bashio::exit.nok "Option 'client_id' must be the Application (client) ID (a GUID) of your Azure app registration."
fi
if [[ ! "${tenant_id}" =~ ^[A-Za-z0-9.-]+$ ]]; then
    bashio::exit.nok "Option 'tenant_id' is invalid. Use 'consumers' for personal Microsoft accounts."
fi
# No token configured: generate one and store it in the add-on options, where the
# Configuration tab shows it as a password field (reveal to copy). Clearing the
# field and restarting rotates it. The value is never written to the log.
if ! bashio::config.has_value 'access_token'; then
    access_token=$(head -c 32 /dev/urandom | od -An -v -tx1 | tr -d ' 
')
    bashio::addon.option 'access_token' "${access_token}" || true
    # bashio does not reliably report API failures, so read the option back.
    if [[ "$(bashio::config 'access_token')" != "${access_token}" ]]; then
        bashio::exit.nok "Could not store the generated access_token. Set the 'access_token' option manually."
    fi
    bashio::log.notice "Generated a new access_token. Open the Configuration tab, reveal 'access_token' and copy it."
fi
# The token is written into the nginx config, so the charset is restricted.
if [[ ! "${access_token}" =~ ^[A-Za-z0-9._~+/=-]{32,128}$ ]]; then
    bashio::exit.nok "Option 'access_token' must be 32-128 characters from [A-Za-z0-9._~+/=-]. Generate one with: openssl rand -hex 32"
fi

# ------------------------------------------------------------ environment
export MS365_MCP_CLIENT_ID="${client_id}"
export MS365_MCP_TENANT_ID="${tenant_id}"
if bashio::config.has_value 'client_secret'; then
    MS365_MCP_CLIENT_SECRET=$(bashio::config 'client_secret')
    export MS365_MCP_CLIENT_SECRET
fi

# Persist the MSAL token cache (+ its .cache-key) and selected account in /data.
export MS365_MCP_TOKEN_CACHE_PATH=/data/.token-cache.json
export MS365_MCP_SELECTED_ACCOUNT_PATH=/data/.selected-account.json
# No system credential store in the container; keep the key file next to the cache.
export MS365_MCP_USE_KEYTAR=0

LOG_LEVEL=$(bashio::config 'log_level' 'info')
export LOG_LEVEL
# MS365_MCP_REDACT_PII is deliberately left unset (default: redaction enabled).

if bashio::config.has_value 'enabled_tools'; then
    ENABLED_TOOLS=$(bashio::config 'enabled_tools')
    export ENABLED_TOOLS
fi

# ------------------------------------------------------------------ flags
# Flags that shape the tool surface (also used for --list-permissions below).
surface_args=()
if bashio::config.true 'read_only'; then
    surface_args+=(--read-only)
fi
if bashio::config.has_value 'preset'; then
    surface_args+=(--preset "$(bashio::config 'preset | join(",")')")
fi
if bashio::config.has_value 'allowed_scopes'; then
    surface_args+=(--allowed-scopes "$(bashio::config 'allowed_scopes')")
fi

server_args=(--http "127.0.0.1:${NODE_PORT}" --trust-proxy-auth --no-dynamic-registration)
server_args+=("${surface_args[@]}")
if bashio::config.has_value 'expected_username'; then
    server_args+=(--expected-username "$(bashio::config 'expected_username')")
fi
if bashio::config.has_value 'message_signoff_suffix'; then
    server_args+=(--message-signoff-suffix "$(bashio::config 'message_signoff_suffix')")
fi
if bashio::config.has_value 'public_url'; then
    server_args+=(--public-url "$(bashio::config 'public_url')")
fi
if bashio::config.true 'enable_auth_tools'; then
    server_args+=(--enable-auth-tools)
    bashio::log.warning "Auth tools (login/logout) are enabled. Disable 'enable_auth_tools' once you are logged in."
fi

# Log the Graph permissions this configuration will request (offline, no secrets).
if permissions=$(ms-365-mcp-server "${surface_args[@]}" --list-permissions 2>/dev/null \
        | jq -r '.effectivePermissions | join(", ")' 2>/dev/null) && [[ -n "${permissions}" ]]; then
    bashio::log.info "Graph delegated permissions requested at login: ${permissions}"
fi

# ------------------------------------------------------------------ nginx
# Only /mcp (bearer required) and /healthz are reachable from the LAN. The
# upstream OAuth endpoints (/authorize, /token, /register, ...) are not exposed.
# Host/Origin are rewritten because upstream rejects non-localhost values when
# bound to loopback, and X-Forwarded-For is replaced (not appended) so the
# upstream per-IP rate limit (120 req/min on /mcp) sees the real client.
umask 077
mkdir -p /run/nginx
cat > "${NGINX_CONF}" <<EOF
worker_processes 1;
pid /run/nginx/ms365-mcp.pid;
error_log /dev/stderr warn;

events {
    worker_connections 128;
}

http {
    access_log off;
    server_tokens off;
    default_type application/json;

    limit_req_zone \$binary_remote_addr zone=mcp:1m rate=20r/s;

    server {
        listen ${PROXY_PORT} default_server;
        # Upstream's express.json() caps request bodies at 100 KB regardless of this value.
        client_max_body_size 25m;

        location = /healthz {
            proxy_pass http://127.0.0.1:${NODE_PORT}/;
            proxy_set_header Host localhost:${NODE_PORT};
            proxy_connect_timeout 2s;
            proxy_read_timeout 5s;
        }

        # limit_req runs before auth_request, so unauthenticated floods are throttled too.
        location = /mcp {
            limit_req zone=mcp burst=40 nodelay;
            limit_req_status 429;
            auth_request /_mcp_auth;
            error_page 401 = @mcp_unauthorized;

            proxy_pass http://127.0.0.1:${NODE_PORT}/mcp;
            proxy_http_version 1.1;
            proxy_set_header Host localhost:${NODE_PORT};
            proxy_set_header Origin "";
            proxy_set_header Authorization "";
            proxy_set_header X-Forwarded-For \$remote_addr;
            proxy_buffering off;
            proxy_connect_timeout 5s;
            proxy_read_timeout 180s;
        }

        # Token check. "if ... !=" compares case-sensitively; a "map" lookup does not.
        location = /_mcp_auth {
            internal;
            if (\$http_authorization != "Bearer ${access_token}") {
                return 401;
            }
            return 204;
        }

        location @mcp_unauthorized {
            add_header WWW-Authenticate 'Bearer realm="ms365-mcp"' always;
            return 401 '{"error":"unauthorized"}';
        }

        location / {
            return 404 '{"error":"not_found"}';
        }
    }
}
EOF
umask 022

nginx -t -c "${NGINX_CONF}" || bashio::exit.nok "Generated nginx configuration is invalid."
nginx -c "${NGINX_CONF}" -g 'daemon off;' &

bashio::log.info "MCP endpoint: http://<ha-host>:${PROXY_PORT}/mcp (Authorization: Bearer <access_token>)"
exec ms-365-mcp-server "${server_args[@]}"
