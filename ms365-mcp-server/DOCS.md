# Microsoft 365 MCP Server - Documentation

## 1. Azure app registration (personal account)

1. Open <https://portal.azure.com> -> **Microsoft Entra ID** -> **App registrations** -> **New registration**.
2. Name: `HA MS365 MCP`. Supported account types: **Personal Microsoft accounts only**. ("Accounts in any organizational directory and personal Microsoft accounts" also works; the add-on is personal-only either way.)
3. **Authentication** -> **Advanced settings** -> **Allow public client flows: Yes**. This is required: the one-time login uses the device-code flow.
4. **Redirect URI: none needed.** Device-code login does not redirect anywhere. A `http://<ha-host>:3000/callback` URI is *not* used: the upstream server has no callback route of its own, and this add-on does not expose its OAuth routes at all.
5. Copy the **Application (client ID)** into the add-on option `client_id`. The add-on always uses tenant `consumers` (upstream notes that `common` refresh tokens are rejected for personal accounts), so do not use the directory (tenant) ID from the portal.
6. **API permissions** -> Microsoft Graph -> **Delegated permissions**. The exact list depends on your options; the add-on logs it at every start, for example for `preset: [mail, calendar]`:

   `Calendars.ReadWrite, Mail.ReadWrite, Mail.Send, MailboxSettings.Read, MailboxSettings.ReadWrite, User.Read`

   Look for the line `Graph delegated permissions requested at login` in the add-on log, or run `npx @softeria/ms-365-mcp-server --preset mail,calendar --list-permissions` anywhere with Node.js. Personal accounts consent at first login, so pre-adding them in the portal is optional. `read_only: true` and `preset` shrink the list.
7. A client secret is **not needed** (the login uses a public client). The add-on has no client secret option.

## 2. Add-on options

Set `client_id` and start the add-on. Leave `access_token` empty: the add-on generates one, stores it in the options, and logs a notice (not the value). Open the Configuration tab, click the eye icon on `access_token` and copy it. To rotate, clear the field and restart. You may also set your own (32-128 characters, `openssl rand -hex 32` works). Optional narrowing, strongly recommended for an LLM-facing mailbox: `read_only: true` or a `preset` such as `[mail, calendar]`. See the table in the README for every option.

`dynamic_tools` (default on) shows the client three tools (`search-tools`, `get-tool-schema`, `execute-tool`) instead of about 180, which saves a lot of context. The model searches for the tool it needs and runs it through `execute-tool`; `read_only` and `preset` still decide what can be found and run. Upstream marks discovery as experimental. Because everything runs through one tool, some clients ask for approval on `execute-tool` as a whole rather than per action; use `read_only: true` if you do not want writes at all. Turn `dynamic_tools` off to list every tool directly.

## 3. One-time login

The add-on logs in by itself on start; no MCP client is needed.

1. Start the add-on. If `/data` holds no valid login, the log shows a notice and Microsoft's message with a code. The add-on waits (up to about 15 minutes) before it starts the server.
2. Open <https://microsoft.com/devicelogin> (the link is also in the message), enter the code, sign in as the account in `expected_username`, and approve the permissions. A different account is rejected before anything is stored.
3. The log then says the login was stored and the MCP endpoint starts. The login survives restarts and updates.

If the code expires, the add-on stops with a message; restart it for a new code. If the login ever expires (for example after months unused), the next start asks for a new one automatically. To switch account, change `expected_username` and restart. The login and logout tools are never exposed to MCP clients.

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
- Rate limits: nginx limits `/mcp` to 20 req/s per client IP (burst 40) before the token is checked, so wrong-token floods are throttled too. Upstream's 120 requests/min per client IP on `/mcp` stays on (nginx forwards the real client IP). The token comparison is exact and case-sensitive.
- The endpoint is plain HTTP: the token is visible to anyone sniffing your LAN. Do not forward the port to the internet and do not put it behind a tunnel. Rotate by changing `access_token` and restarting.
- Mail content is untrusted input to the model (prompt injection). Prefer `read_only: true` and a narrow `preset` until you need writes. Outgoing mail gets the `message_signoff_suffix` appended.
- Logs: upstream redacts tokens, JWTs and email addresses (`MS365_MCP_REDACT_PII` left at default). The add-on never prints `access_token`.
- Request bodies are capped at 100 KB by upstream (`express.json()`); larger tool calls, such as big base64 attachments, fail with `413`. The nginx limit of 25 MB is not the effective cap.
- Upstream writes `mcp-server.log`, `error.log` and `audit.log` to `~/.ms-365-mcp-server/logs` inside the container with no rotation. They are lost when the add-on is rebuilt or updated and grow only with usage (about 80 KB per start).
- The add-on process runs as root inside its container; `/data` holds the encrypted token cache plus its key file (`.cache-key`), as upstream does without a system keyring.

## Troubleshooting

- `401` from `/mcp`: wrong or missing bearer token.
- Add-on exits at start: the log names the invalid option (`client_id` must be a GUID, `access_token` 32-128 characters). If the generated token could not be stored, set `access_token` manually.
- `AADSTS7000218` / public client error at login: enable **Allow public client flows** (step 3 of section 1).
- Log line `expected account pinning is configured, but --http uses request-provided tokens ...` is upstream's generic warning. In this add-on (`--trust-proxy-auth`) the pin is enforced at login and when the cached account is resolved.
- The add-on stops with "Microsoft login did not complete": the code expired or the wrong account was used. Restart it and sign in with the account in `expected_username`.
