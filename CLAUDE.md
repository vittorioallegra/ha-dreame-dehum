# ha-dreame-dehum

Home Assistant custom integration (domain `dreame_dehum`) for Dreame
dehumidifiers through the Dreamehome cloud. Python 3.13+, no runtime
requirements beyond Home Assistant.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_dev.txt   # install
.venv/bin/pytest -q -p no:logging                                        # all tests
.venv/bin/pytest -q -p no:logging tests/test_init.py::test_power         # one test, failures only
.venv/bin/ruff format . && .venv/bin/ruff check --fix .                  # format + lint
.venv/bin/mypy custom_components                                         # types
python3 tools/probe.py --help                                            # map a device (needs a Dreamehome account)
```

No build step; CI (`.github/workflows`) runs ruff, mypy, pytest, hassfest and
the HACS action.

## Layout

- `custom_components/dreame_dehum/` — the integration
  - `api.py` — Dreame cloud client (login, device list, get/set properties)
  - `profiles.py` — per-model property maps; pure data
  - `device.py` — guarded access: refuses anything a profile doesn't declare
  - `coordinator.py` — polling, post-write refresh, error mapping
  - one module per platform (`humidifier`, `sensor`, `switch`, ...)
  - `strings.json` + `translations/` — UI text (English base, Italian)
- `tests/` — pytest with a `FakeCloud` stand-in (`tests/conftest.py`)
- `tools/probe.py` — standalone, stdlib-only mapping tool (sweep / learn / write)

## Conventions

- Entities never call the cloud directly; everything goes through
  `DreameDevice`, and only addresses and values listed in the model's
  `Profile` are read or written. Unknown models get no entities.
- Never guess a property or action on a real device: map it with
  `tools/probe.py` and record how it was confirmed in the profile's comment.
- Property 7/3 on the DD20 is a location string: never read or log it.
- The repo is public: no real account data, device IDs, MACs, serials or
  locations in code, tests, fixtures or docs. Probe reports
  (`sweep-*.json`, `learn-*.json`) are gitignored.
- `strings.json` and `translations/en.json` must stay identical.
- Releases: bump `version` in `manifest.json` and `pyproject.toml`, then publish
  a GitHub release tagged `vX.Y.Z` on that commit; HACS shows release names.
