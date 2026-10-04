## 1. Add-on

- [x] 1.1 Add `ms365-mcp-server/` with config, Dockerfile, run.sh, README, DOCS, CHANGELOG, icons.
- [x] 1.2 nginx bearer gate and route restriction.
- [x] 1.3 Option-to-flag mapping and startup validation.

## 2. Validation

- [x] 2.1 addon-linter passes (non-community mode); shellcheck clean.
- [x] 2.2 Image builds; `/mcp` returns 401 without a valid token and answers `initialize` / `tools/list` with it.
- [ ] 2.3 Azure app registration and device-code login with the real account (requires the owner).

## 3. Documentation

- [x] 3.1 Root README, `repository.json`, `AGENTS.md` list the add-on.
