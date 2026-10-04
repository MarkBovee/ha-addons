## ADDED Requirements

### Requirement: Bearer-protected MCP endpoint
The add-on SHALL expose the MCP endpoint on container port 3000 only through a reverse proxy that requires `Authorization: Bearer <access_token>`.

#### Scenario: Missing or wrong token
- **WHEN** a client calls `/mcp` without the configured token
- **THEN** the proxy SHALL answer 401 and the request SHALL NOT reach the MCP server

#### Scenario: Token with different case or prefix
- **WHEN** a client sends the token with different letter case, a lowercase `bearer` scheme, or extra whitespace
- **THEN** the proxy SHALL answer 401 (the comparison is exact and case-sensitive)

#### Scenario: Valid token
- **WHEN** a client calls `/mcp` with the configured token
- **THEN** the request SHALL be forwarded to the MCP server bound to `127.0.0.1`

#### Scenario: No token configured
- **WHEN** `access_token` is empty
- **THEN** the add-on SHALL generate a 64-character hex token, store it in its own options, and SHALL NOT log its value

#### Scenario: Invalid token
- **WHEN** `access_token` is shorter than 32 characters, longer than 128, or contains characters outside `[A-Za-z0-9._~+/=-]`
- **THEN** the add-on SHALL refuse to start with a clear log message

### Requirement: Restricted route surface
The proxy SHALL expose only `/mcp` and `/healthz`.

#### Scenario: Upstream OAuth routes
- **WHEN** a client requests `/authorize`, `/token`, `/register`, `/.well-known/*` or `/callback`
- **THEN** the proxy SHALL answer 404

### Requirement: Persistent single-account login
The add-on SHALL keep the MSAL token cache and selected account in `/data` and SHALL pin the login to `expected_username` when set.

#### Scenario: Restart or update
- **WHEN** the add-on restarts or is updated
- **THEN** the previous login SHALL still be usable without logging in again

### Requirement: Option mapping without invented flags
The add-on SHALL translate options only to documented upstream flags and environment variables and SHALL leave PII redaction at its default.

#### Scenario: Read-only and preset options
- **WHEN** `read_only` is true and `preset` is `[mail, calendar]`
- **THEN** the server SHALL start with `--read-only --preset mail,calendar`

### Requirement: No public exposure
The add-on SHALL NOT enable ingress or host networking.

#### Scenario: Network configuration
- **WHEN** the add-on is installed
- **THEN** it SHALL publish only `3000/tcp`, with a user-configurable host port
