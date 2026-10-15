# Changelog

All notable changes to the Microsoft 365 MCP Server add-on will be documented in this file.

## [0.5.0] - 2026-10-04

### Added
- Option `dynamic_tools` (default on) starts the server with upstream's experimental `--discovery`: clients see `search-tools`, `get-tool-schema` and `execute-tool` instead of about 180 tools. `read_only` and `preset` still restrict what can be found and executed (verified: with `read_only` and a mail/calendar preset there are 27 searchable tools and `send-mail` is "not found"). Turn it off to list every tool directly.

## [0.4.1] - 2026-10-04

### Fixed
- The device-code URL and code were not shown in the add-on log until the login had finished, because the output went through a buffering `grep`. Lines are now passed on immediately.

## [0.4.0] - 2026-10-04

### Changed
- The one-time Microsoft login now happens in the add-on: when `/data` has no valid login, the device-code URL and code are printed in the add-on log and the server starts after sign-in.
- Removed `enable_auth_tools`; the login and logout tools are no longer exposed to MCP clients.

## [0.3.1] - 2026-10-04

### Changed
- `access_token` moved to the bottom of the configuration and all options got names and descriptions (English and Dutch). The description says the token is generated automatically and normally must not be filled in.

## [0.3.0] - 2026-10-04

### Changed
- Simplified configuration from 13 to 6 options. Removed `tenant_id` (fixed `consumers`), `client_secret`, `enabled_tools`, `allowed_scopes`, `public_url` and `log_level` (fixed `info`).
- `expected_username` now defaults to `user@outlook.com`; set your own account.

### Fixed
- Supervisor refused to save the configuration ("expected a URL") because `public_url` defaulted to an empty string.

## [0.2.0] - 2026-10-04

### Added
- `access_token` is now optional. When empty, the add-on generates a 64-character hex token on start and stores it in its own options, so it can be revealed and copied from the Configuration tab. Clearing the field and restarting rotates it. The token is never logged.

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
