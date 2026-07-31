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
