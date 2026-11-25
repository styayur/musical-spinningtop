# Offline artwork

The plates are original line drawings. They are not posters, production stills, or Wikipedia images, and they must not be credited as such.

## What it does

`artwork/` reads the same merged local fields used by the page: stable id, titles, and Chinese or English summaries. It normalizes text, matches a small maintained lexicon, chooses a composition family from synopsis evidence, and writes an SVG. The browser only displays the result.

A new catalogue row with those local fields is handled by the same rules. There is no per-show override table, no remote model, and no copied poster.

This is an interpretation of explicit phrases in the supplied text. It is not a claim that the program understands the plot, the production, or the historical setting. Empty or insufficient text uses a recorded abstract theatre plate. The generator does not invent people, places, periods, or events to make a richer picture.

## Offline boundary

Normalization, extraction, composition, and SVG writing use the Python standard library and can run with the network disabled.

Refreshing Wikipedia data is a separate online step. A GitHub Pages visit that has never downloaded the site is not an offline first open. After the static files are cached by the browser, the algorithm plates themselves do not need a remote image host. Unverified remote covers stay in the data but are not the main image.

## Both entry points

`build_site.py` generates `static/artwork/*.svg` and a manifest after merging the publication snapshot. Relative `./static/artwork/` URLs work at the site root and under `/musical-spinningtop/`.

The Flask app uses the same `plan_artwork` path. It caches SVGs under the runtime data directory and serves only names that match `base.svg` or a 20-character hex digest. A detail refresh rewrites that work's plate when its source digest changes. It does not redraw the daily selection.

The same normalized input and generator version produce the same SVG in both entry points. Seeds come from SHA-256 of the stable id and a purpose string. They do not use `hash()`, the clock, catalogue order, or the draw random source.

`art_version` and `extractor_version` live in `artwork/versions.py`. Bump them when a rule or drawing change should invalidate cached plates. `source_digest` covers the id, titles, and summaries, so an unrelated catalogue reorder does not rebuild another work.

## Display and history

`image` and `image_source` remain the remote-art fields. `artwork_url` and `artwork_kind` are the algorithm plate. A remote URL is shown only when `image_reuse` is `verified` and the URL is HTTPS. The bundled snapshot does not mark covers verified, so the main image is the original plate.

Image states are `no-original`, `loading`, `loaded`, `failed`, and the generated fallback. A failed cover does not draw another show. A generation token drops stale image callbacks.

IndexedDB daily rows keep their show id. On read, the static client replaces a still-present show with the current catalogue row and plate. An old full object is kept only when that id has left the catalogue, and it then uses the bundled `base.svg`. Flask keeps the saved daily id and joins the latest catalogue and detail cache; a removed id still resolves to a safe local plate. Neither path clears seen-cycle history or redraws an old date.

## Visual rules

Shared parts are the palette, line weight, margin, and the relationship between plate and title. The title stays in HTML. Variation is meant to come from the subject, count, arrangement, and family: relation, city, stage, route, terrain, portal, still, or abstract.

Colour and a mirror flag are derived supplements. They do not choose the family. Identical abstract plates are the insufficient-evidence fallback, not evidence that every show was understood.

Scores are heuristic sort keys. They are not calibrated probabilities. Negation is local. `without love` / `没有爱` is down-weighted rather than treated as proof that love is absent. Titles cannot by themselves select a family. Production and genre boilerplate is down-weighted. Duplicate Chinese and English text is scored once.

## Budget

Each SVG is built from a fixed element set. Text from the catalogue is not interpolated into path data, scripts, or file names. The writer rejects script, foreignObject, event attributes, external images, external fonts, and arbitrary links.

The initial 5-25KB size target was revised after measuring the line plates. Typical files are about 0.7-5.4KB. Padding them to 5KB would add noise, so it is not done. The hard cap remains 60KB and 220 drawing nodes; over-budget output falls back to the abstract plate and records `budget`.

## Review pack

From the repository root:

```powershell
python scripts/artwork_review.py
```

This writes `docs/artwork-review/` from the committed snapshot. The sample seed is `spinningtop-artwork-sample-2026-11-25`. Abstract count is coverage with a recorded reason, not a count of understood plots. Low structural similarity is not treated as a quality score.

Regenerate the pack when the lexicon, composition, or drawing changes. Do not commit `_site/`, `data/runtime/`, or a user's draw database.
