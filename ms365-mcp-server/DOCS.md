# Microsoft 365 MCP Server - Documentation

## 1. Azure app registration (personal account)

1. Open <https://portal.azure.com> -> **Microsoft Entra ID** -> **App registrations** -> **New registration**.
2. Name: `HA MS365 MCP`. Supported account types: **Personal Microsoft accounts only**. ("Accounts in any organizational directory and personal Microsoft accounts" also works; the add-on is personal-only either way.)
3. **Authentication** -> **Advanced settings** -> **Allow public client flows: Yes**. This is required: the one-time login uses the device-code flow.
4. **Redirect URI: none needed.** Device-code login does not redirect anywhere. A `http://<ha-host>:3000/callback` URI is *not* used: the upstream server has no callback route of its own, and this add-on does not expose its OAuth routes at all.
5. Copy the **Application (client ID)** into the add-on option `client_id`. Leave `tenant_id` at `consumers` (upstream notes that `common` refresh tokens are rejected for personal accounts).
6. **API permissions** -> Microsoft Graph -> **Delegated permissions**. The exact list depends on your options; the add-on logs it at every start, for example for `preset: [mail, calendar]`:

   `Calendars.ReadWrite, Mail.ReadWrite, Mail.Send, MailboxSettings.Read, MailboxSettings.ReadWrite, User.Read`

   Look for the line `Graph delegated permissions requested at login` in the add-on log, or run `npx @softeria/ms-365-mcp-server --preset mail,calendar --list-permissions` anywhere with Node.js. Personal accounts consent at first login, so pre-adding them in the portal is optional. `read_only: true` and `allowed_scopes` shrink the list.
7. A client secret is **not needed** (the login uses a public client). `client_secret` may stay empty.

## 2. Add-on options

Set `client_id` and `access_token` (generate the token with `openssl rand -hex 32`), then start the add-on. Optional narrowing, strongly recommended for an LLM-facing mailbox: `read_only: true`, a `preset` such as `[mail, calendar]`, or an `enabled_tools` regex. See the table in the README for every option.

## 3. One-time login

Login uses upstream's `login` / `verify-login` tools, which are only registered while `enable_auth_tools` is `true` (default).

1. Connect a client as described in section 4.
2. Ask it to call the `login` tool. It returns a message with a URL (<https://microsoft.com/devicelogin>) and a code.
3. Open the URL, enter the code, sign in as the account in `expected_username`, and approve the permissions. A different account is rejected before anything is stored.
4. Call `verify-login`. It should report success.
5. Set `enable_auth_tools: false` and restart. The cached login in `/data` survives restarts and updates; the `logout` tool is no longer exposed to the model.

If the login ever expires (for example after months unused), set `enable_auth_tools: true` again and repeat.

## 4. Client configuration

URL: `http://<ha-host>:3000/mcp` (use your configured host port). Header: `Authorization: Bearer <access_token>`.

**Claude Code**

```bash
claude mcp add --transport http ms365 http://<ha-host>:3000/mcp \
  --header "Authorization: Bearer <access_token>"
```

Or in `.mcp.json` (environment variables are expanded):

```json
{
  "mcpServers": {
    "ms365": {
      "type": "http",
      "url": "http://<ha-host>:3000/mcp",
      "headers": { "Authorization": "Bearer ${MS365_MCP_HA_TOKEN}" }
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`) has no plain-HTTP server entry, so use the `mcp-remote` bridge. `--allow-http` is needed because the endpoint is plain HTTP on your LAN; the value has no space after the colon, the space lives in the env var (per mcp-remote's documentation):

```json
{
  "mcpServers": {
    "ms365": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote", "http://<ha-host>:3000/mcp",
        "--allow-http",
        "--header", "Authorization:${MS365_AUTH}"
      ],
      "env": { "MS365_AUTH": "Bearer <access_token>" }
    }
  }
}
```

## Security

What was verified in the upstream source (v0.158.0) and what it means here:

- Default `--http` mode only checks that an `Authorization: Bearer ...` header exists and is not an expired JWT; the real validation is Microsoft Graph rejecting the token. It never uses the cached login.
- With `--trust-proxy-auth` (used here) that check is skipped and **every caller uses the cached login**. Anyone who can reach the MCP server can read and send your mail. Hence nginx enforces `access_token` on `/mcp`, the MCP server listens on `127.0.0.1` only, and `/authorize`, `/token`, `/register` and `/.well-known/*` return 404 (dynamic client registration is also off via `--no-dynamic-registration`).
- Rate limits: upstream's 120 requests/min per client IP on `/mcp` stays on (nginx forwards the real client IP); nginx additionally limits to 20 req/s per IP.
- The endpoint is plain HTTP: the token is visible to anyone sniffing your LAN. Do not forward the port to the internet and do not put it behind a tunnel. Rotate by changing `access_token` and restarting.
- Mail content is untrusted input to the model (prompt injection). Prefer `read_only: true` and a narrow `preset` until you need writes. Outgoing mail gets the `message_signoff_suffix` appended.
- Logs: upstream redacts tokens, JWTs and email addresses (`MS365_MCP_REDACT_PII` left at default). The add-on never prints `access_token` or `client_secret`.
- The add-on process runs as root inside its container; `/data` holds the encrypted token cache plus its key file (`.cache-key`), as upstream does without a system keyring.

## Troubleshooting

- `401` from `/mcp`: wrong or missing bearer token.
- Add-on exits at start: the log names the invalid option (`client_id` must be a GUID, `access_token` 32-128 characters).
- `AADSTS7000218` / public client error at login: enable **Allow public client flows** (step 3 of section 1).
- `verify-login` says the expected account is not in the cache: run `login` again.
