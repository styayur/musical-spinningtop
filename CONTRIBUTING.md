# Contributing

Spinning Top has two deliberate surfaces: a Python local app and a static GitHub Pages version. Keep their differences documented and tested.

## Development

Python 3.9+ is supported.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\validate_catalog.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe app.py
```

For the static site:

```powershell
.venv\Scripts\python.exe build_site.py
python -m http.server 8080 --directory _site
python tests/site_smoke.py
```

## Data changes

- Run `catalog.py` and `cache_articles.py` only against the documented Wikipedia source categories.
- Record the snapshot date, row count, source URL, and command in [docs/data-provenance.md](docs/data-provenance.md).
- Run `scripts/validate_catalog.py`; duplicate ids, page ids, titles, missing articles, and orphan articles fail the build.
- Keep article attribution and `intro_source` intact.
- Do not commit `data/runtime/`, SQLite databases, caches, generated `_site/`, or private draw history.
- Images remain externally hosted and have individual licenses; code licensing does not replace content licensing.

## Pull requests

Add regression tests for discovery, storage, catalogue validation, or static-site behavior. Include screenshots for visible UI changes. Maintainers perform releases and deploy Pages.

Security issues must follow [SECURITY.md](SECURITY.md), not the public issue tracker.
