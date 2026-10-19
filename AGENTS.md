# AGENTS.md

Guidance for AI coding agents working on this repository.

## Project

Custom Home Assistant integration ("Lissy Library") that scrapes a
Lissy-based public library portal for borrowed items, due dates, and
loan renewals. Single domain `lissy` under `custom_components/lissy/`.

## Verification commands

Run **all** of these before considering work complete. They mirror the
CI pipeline in `.github/workflows/pythonpackage.yml`.

```bash
# Formatting
black --check .

# Type checking
mypy custom_components/lissy --ignore-missing-imports

# Tests
pytest -q

# Security
bandit -r custom_components/ -ll
```

A Python 3.14 virtualenv with `requirements_test.txt` provides every
tool. The hassfest / HACS validators run separately in CI
(`validate.yaml`); device filters are **not** allowed in a service
`target` block — use a `fields` entry with a `device` selector
instead (see `services.yaml`).

## Commit conventions

Conventional Commits style, lowercase imperative subject, scoped:

```
type(scope): subject
```

Common scopes: `lissy` (general / cross-module), `config_flow`,
`sensor`, plus module names as needed (`api`, `coordinator`). Keep the
subject lowercase, no trailing period. Body wrapped ~72 cols,
paragraphs separated by blank lines, explaining the *why*.

Examples from this repo:
- `fix(lissy): guard unset runtime_data and empty renew target set`
- `feat(config_flow): reject base_url that doesn't end with lissy/lissy.ly`
- `test(lissy): assert LissyClient._login hits the configured base_url`

Keep PR history clean, no fix-forward ping-pong: when a commit already
in your PR turns out wrong (say a validator rejects a manifest key),
rebase, squash or rewrite it so the PR reads as if it were written
correctly the first time — own branches may be force-pushed.

## Code conventions

- `from __future__ import annotations` in every module.
- TypedDicts for API data (`LoanItem`, `RenewResult`, `RenewResponse`).
- `StrEnum` for `MediaType`.
- Error taxonomy: `LissyAuthError`, `LissyConnectionError` in
  `api.py`; map to `ConfigEntryAuthFailed` / `UpdateFailed` in the
  coordinator and to `ServiceValidationError` / `HomeAssistantError`
  in the service handler.
- Raw responses are decoded as `latin-1` (Lissy portals are German);
  umlauts depend on this today

## Home Assistant compatibility

- CI installs the latest `pytest-homeassistant-custom-component`, so
  `mypy` and `pytest` always run against the newest stable Home
  Assistant (it resolved HA 2026.10 when probatio's typing landed).
  Verify locally against latest before pushing — a pinned older HA in
  the dev venv hides failures that CI will hit.
- Flow schemas build with `probatio`, HA's typed schema engine first
  shipped in 2026.9 and the primary typed engine since 2026.10:
  `ConfigFlow.async_show_form` is typed against
  `probatio.schema.Schema`, so `voluptuous` schemas fail mypy on
  current CI. probatio is a drop-in for the flow usage here
  (`Required(..., default=)`, selectors as values).
- The minimum Home Assistant version is declared in `hacs.json`
  (`"homeassistant": "<version>"`) and noted in the README install
  section. Never put a `homeassistant` key in `manifest.json` —
  hassfest's schema for custom-integration manifests rejects it. HA
  itself does not gate custom integrations by version, so non-HACS
  installs will fail with an ImportError; the README sets the
  expectation there.
- `scripts/start-ha.sh` pulls the latest `:stable` HA image on every
  start: compose otherwise reuses a stale image forever, and a stale
  local HA misleads tests and manual checking.
