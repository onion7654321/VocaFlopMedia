# Contributing

Bug reports and feature proposals are welcome. Before submitting an issue, check existing issues and reproduce the problem with the latest applicable release.

## Development checks

Use Python 3.12 in an isolated virtual environment and install `.[build,dev]` as described in [BUILDING.md](BUILDING.md). Run:

```sh
python -m pip check
python -m ruff check app scripts tests main.py
python -m unittest discover -s tests -q
```

Keep changes focused, include regression tests when practical, and describe which operating systems were tested. Do not include build outputs, local settings, download history or credentials. A successful build does not replace a native smoke test.

A source-code license has not yet been selected. Discuss proposed code contributions with the maintainer before submitting them; no additional license grant is implied by this guide.
