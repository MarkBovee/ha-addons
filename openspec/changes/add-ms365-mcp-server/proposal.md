## Why

Claude Desktop and Claude Code on the home network should be able to use a personal Outlook/Hotmail mailbox and calendar through MCP. The MIT-licensed npm package `@softeria/ms-365-mcp-server` provides the tools, but its HTTP mode is designed as a stateless multi-user OAuth proxy, not as a single-identity LAN service. Running it on Home Assistant needs a thin wrapper that keeps one persisted login and adds the missing access control.

## What Changes

- Add the `ms365-mcp-server` add-on (slug `ms365_mcp_server`, `amd64` + `aarch64`) that installs a pinned upstream npm release and runs it with `--http` and `--trust-proxy-auth`.
- Put nginx in front of it to enforce a configured bearer token on `/mcp`, expose only `/mcp` and `/healthz`, and keep the MCP server on `127.0.0.1`.
- Persist the MSAL token cache and selected account in `/data`.
- Map add-on options to upstream flags and environment variables; no flags are invented.
- Document Azure app registration (personal accounts), the one-time device-code login, and Claude Desktop / Claude Code client configuration.

## Capabilities

### New Capabilities
- `ms365-mcp-server`: LAN-only, bearer-protected MCP access to one personal Microsoft account.

### Modified Capabilities

None.

## Impact

- New directory `ms365-mcp-server/`; root `README.md`, `repository.json` and `AGENTS.md` list it.
- No Home Assistant entities, no MQTT, no dependency on other add-ons; unrelated to HEMS.
- Out of scope: public exposure, tunnels, TLS termination, org/work-account mode.
