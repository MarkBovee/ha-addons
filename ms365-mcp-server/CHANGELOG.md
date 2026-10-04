# Changelog

All notable changes to the Microsoft 365 MCP Server add-on will be documented in this file.

## [0.1.1] - 2026-10-04

### Fixed
- The bearer token comparison is now case-sensitive. nginx `map` lookups are not, so `bearer <token>` and an upper-cased token were accepted.
- Unauthenticated requests to `/mcp` are now covered by the nginx rate limit (the token check moved to `auth_request`, which runs after `limit_req`).

### Changed
- Docs: the effective request body cap is 100 KB (upstream `express.json()`), upstream log files are unbounded, and the nginx rate limit wording was corrected.

## [0.1.0] - 2026-10-04

### Added
- Initial release wrapping `@softeria/ms-365-mcp-server` 0.158.0 for a personal Outlook/Hotmail account.
- nginx bearer-token gate (`access_token`) in front of the MCP server; only `/mcp` and `/healthz` are exposed.
- Token cache and selected account persisted in `/data`.
- Docker `HEALTHCHECK` against `/healthz`; startup log lists the Graph permissions requested at login.
