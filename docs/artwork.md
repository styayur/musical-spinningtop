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

The Flask app uses the same `plan_artwork` path after the same publication merge, including a bundled Chinese summary. It caches SVGs under the runtime data directory. A served name is `base.svg` or a versioned name containing the art version, extractor version, source digest, and show id. Old and new plates therefore do not share a file. A detail refresh writes a new file when the digest changes. It does not redraw the daily selection, and a late older write must not replace bytes already published at a newer URL.

The same normalized input and generator version produce the same SVG in both entry points. Seeds come from SHA-256 of the stable id and a purpose string. They do not use `hash()`, the clock, catalogue order, or the draw random source.

`art_version` and `extractor_version` live in `artwork/versions.py`. Bump them when a rule or drawing change should invalidate cached plates. `source_digest` covers the id, titles, and summaries, so an unrelated catalogue reorder does not rebuild another work.

Publication uses an OS file lock as well as a thread lock (Windows byte-range locking; POSIX flock). Planning runs outside the shared manifest lock. Equal requests share a separate request lock, and recheck the cache before extracting. Atomic replacement publishes complete files; an existing versioned URL with different bytes is rejected. Old SVGs are retained so already-issued URLs remain valid. Runtime directories can therefore grow with revisions. Temporary files from interrupted publishers are recovered under the publication lock.

## Display and history

`image` and `image_source` remain the remote-art fields. `artwork_url` and `artwork_kind` are the algorithm plate. A remote URL is shown only when `image_reuse` is `verified` and the URL is HTTPS. The bundled snapshot does not mark covers verified, so the main image is the original plate.

Image states are `no-original`, `loading`, `loaded`, `failed`, and the generated fallback. A failed cover does not draw another show. A generation token drops stale image callbacks.

IndexedDB daily rows keep their show id and a small archive: version, titles, summaries, source URL, and year. Reading a still-present show displays the current catalogue row, without shrinking that archive to `{id,v:2}`. After the id leaves the catalogue, the archive still supplies the title, summary, and source, and the image is `base.svg`. Flask keeps the saved daily id and joins the latest catalogue and detail cache; a removed id uses the saved text and the same base plate. Neither path clears seen-cycle history or redraws an old date. A generated SVG that returns 404 falls back once to `base.svg`; a failed base image does not retry, and the failure does not draw another show.

## Visual rules

Shared parts are the palette, line weight, margin, and the relationship between plate and title. The title stays in HTML. Variation is meant to come from the subject, count, arrangement, and family: relation, city, stage, route, terrain, portal, still, or abstract. Insufficient text uses one of eight abstract line templates. Those templates differ by overlap, density, and spacing. Colour and mirroring only supplement that choice. An abstract plate has an empty basis and is not described as a person, place, or event from the plot.

Colour and a mirror flag are derived supplements. They do not choose the family. The displayed basis lists only motifs the plate actually draws. A repeated opening title, a venue such as Garden Theatre, and a creator's dated death are not plot evidence. The first non-negated count is the count that is drawn. Chinese negation applies only to the immediately following phrase.

Scores are heuristic sort keys. They are not calibrated probabilities, and a hit rate is not a plot-understanding score. Negation is local. `without love` / `没有爱` is down-weighted rather than treated as proof that love is absent. Titles cannot by themselves select a family. Production and genre boilerplate is down-weighted. Duplicate Chinese and English text is scored once. `error` and `insufficient` are different recorded reasons.

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
