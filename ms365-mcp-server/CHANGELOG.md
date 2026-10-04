# Changelog

All notable changes to the Microsoft 365 MCP Server add-on will be documented in this file.

## [0.1.0] - 2026-10-04

### Added
- Initial release wrapping `@softeria/ms-365-mcp-server` 0.158.0 for a personal Outlook/Hotmail account.
- nginx bearer-token gate (`access_token`) in front of the MCP server; only `/mcp` and `/healthz` are exposed.
- Token cache and selected account persisted in `/data`.
- Docker `HEALTHCHECK` against `/healthz`; startup log lists the Graph permissions requested at login.
