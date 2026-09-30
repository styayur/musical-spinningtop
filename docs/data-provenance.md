# Data provenance and rebuild contract

The committed catalogue is a dated snapshot, not a live mirror.

| Snapshot | Value |
| --- | --- |
| Catalogue updated | `2026-09-24T16:36:48.116681+00:00` |
| Catalogue rows | 2,650 |
| Article summaries updated | `2026-09-24T16:45:48.609609+00:00` |
| Article summaries | 2,676 (including saved entries that may no longer be in the current catalogue) |
| Catalogue source | https://en.wikipedia.org/wiki/Category:Musicals_by_year |
| Article text license | CC BY-SA 4.0 |
| Image license | Individual, recorded per source page; images are not bundled |

## Rebuild

From the repository root with dependencies installed:

```powershell
python catalog.py
python cache_articles.py
python scripts/validate_catalog.py
python -m unittest discover -s tests -v
```

`catalog.py` discovers entries from year categories, excludes configured non-target pages, de-duplicates Wikipedia page IDs, and replaces `data/catalog.json` only after a successful complete crawl. `cache_articles.py` updates `data/articles.json`. The weekly Pages workflow performs the same refresh in a clean runner; a failed refresh keeps the previous deployment.

## Lifecycle boundary

- Application and static-site versions are release-scoped.
- Catalogue and article snapshots are data-scoped; their `updated_at` values can change without an application release.
- `data/runtime/` stores local draw history and dynamic article cache. It is intentionally untracked.
- The static site serves a generated snapshot from `_site/data/site-catalog.json`; it does not commit deployment output to `main`.

