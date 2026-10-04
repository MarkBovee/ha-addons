## Context

Upstream `--http` (verified against v0.158.0): `/mcp` requires an `Authorization: Bearer` header that is only checked for presence and JWT expiry; Graph calls then use the caller's own Microsoft token, and the MSAL cache is not used. OAuth routes (`/authorize`, `/token`, `/register`) are served by the same process, and the server has no `/callback` route of its own.

`--trust-proxy-auth` removes the bearer check and makes all callers share the cached MSAL identity (same path as stdio mode). That is the only upstream mode that supports "log in once, clients use static credentials".

## Decisions

- Use `--trust-proxy-auth` and make nginx the only network-reachable listener; the MCP server binds `127.0.0.1:3001`. Without nginx, anyone on the LAN would act as the mailbox owner, so the add-on refuses to start without a valid `access_token`.
- Login via upstream's `--login` device-code flow, run by the add-on before the server starts so the code appears in the add-on log (no browser redirect is possible for a headless LAN service). The MCP login/logout tools are not exposed.
- Expose only `/mcp` and `/healthz`; add `--no-dynamic-registration` as defence in depth.
- Health: Docker `HEALTHCHECK` on nginx `/healthz` (proxied to the upstream root route). `/mcp` needs POST plus a token, so it is not a usable probe.
- Install with `--ignore-scripts` and `MS365_MCP_USE_KEYTAR=0`: the optional native keytar module cannot build on musl and there is no system keyring.

## Risks

- Plain HTTP on the LAN exposes the bearer token to sniffing; documented, public exposure out of scope.
- A leaked token grants full mailbox access within the enabled tools; mitigated by `read_only` and `preset`.
- Upstream flag changes between versions; the version is pinned and bumped deliberately.
