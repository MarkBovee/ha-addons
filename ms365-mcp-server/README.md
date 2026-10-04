# Microsoft 365 MCP Server

LAN-only [MCP](https://modelcontextprotocol.io) server for one personal Outlook/Hotmail account. It wraps the MIT-licensed npm package [`@softeria/ms-365-mcp-server`](https://github.com/softeria/ms-365-mcp-server) (mail, calendar, contacts, OneDrive, ... through Microsoft Graph) so Claude Desktop and Claude Code on your network can use it.

- Pinned upstream version: `0.158.0` (Docker build arg `MS365_MCP_VERSION`)
- Architectures: `amd64`, `aarch64`
- No ingress, no host network, no public exposure. Personal accounts only (no org mode).
- Entities: none. Dependencies on other add-ons: none.

## How it is protected

Upstream's `--http` mode is built as a stateless OAuth proxy for multi-user hosting. This add-on instead runs it with `--trust-proxy-auth`, so every caller shares the one login stored in `/data`. In that mode the MCP server performs **no** authentication of its own. nginx therefore sits in front of it and requires `Authorization: Bearer <access_token>` on `/mcp`. Only `/mcp` and `/healthz` are reachable; the upstream OAuth routes are not exposed. Details in [DOCS.md](DOCS.md#security).

## Install

1. Add `https://github.com/MarkBovee/ha-addons` in `Settings -> Add-ons -> Add-on Store -> Repositories`.
2. Install **Microsoft 365 MCP Server**.
3. Register the Azure app (see [DOCS.md](DOCS.md)), set `client_id` and `expected_username`, start the add-on and sign in with the code shown in its log.

## Configuration

| Option | Default | Maps to |
| --- | --- | --- |
| `client_id` | - (required) | `MS365_MCP_CLIENT_ID` |
| `access_token` (bottom, generated) | empty = generated on first start and stored here; or your own, 32-128 chars | bearer token checked by nginx |
| `expected_username` | `user@outlook.com` (set your own account) | `--expected-username` |
| `read_only` | `false` | `--read-only` |
| `preset` | empty (all personal tools) | `--preset a,b` |
| `message_signoff_suffix` | `Sent via Claude` | `--message-signoff-suffix` |

Fixed by the add-on: `MS365_MCP_TENANT_ID=consumers` (personal accounts only), `LOG_LEVEL=info`, `--http 127.0.0.1:3001`, `--trust-proxy-auth`, `--no-dynamic-registration`, `MS365_MCP_TOKEN_CACHE_PATH=/data/.token-cache.json`, `MS365_MCP_SELECTED_ACCOUNT_PATH=/data/.selected-account.json`, `MS365_MCP_USE_KEYTAR=0`. `MS365_MCP_REDACT_PII` is left at its default (redaction on).

The host port is configurable under the add-on's Network tab (container port `3000/tcp`).
