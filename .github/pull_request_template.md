## Summary

## Why

## Validation

- [ ] `python scripts/validate_catalog.py` passes.
- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `python build_site.py` and `python tests/site_smoke.py` pass when static-site code changes.
- [ ] Catalogue/rebuild changes document snapshot date, command, source, and provenance.
- [ ] No runtime SQLite, cache, private history, or generated deployment output is committed.

## Compatibility

Describe changes to catalogue schema, IndexedDB/SQLite persistence, data licensing, local/static feature parity, or supported Python version.
