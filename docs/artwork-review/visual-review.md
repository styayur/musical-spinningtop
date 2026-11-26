# Artwork visual review — 2026-11-26

The final v4 pack visibly reduces the original baseline's repeated triangle plate. The originally independent v3 sample exposed three source-context errors and drove bounded generic fixes. The same IDs now demonstrate those fixes as regression evidence, **not blind or held-out evidence**. The drawings still repeat and do not establish plot understanding. This is a local visual/evidence review, not a deployment or remote-CI record.

## Evidence and reproducibility

Original HEAD was `91d44bc3a81c805164376564e7c59547fb2661f6`. Its tracked PNG, SVG and JSON files are preserved byte-for-byte under [baseline/](baseline/), with SHA-256 values in [baseline/provenance.json](baseline/provenance.json). Extraction used binary `subprocess` output from `git show` and `Path.write_bytes`, never PowerShell text redirection. The original [baseline/stats.json](baseline/stats.json) is unchanged. Its 214 structural signatures are metadata combinations, not geometry diversity.

[baseline/metrics.json](baseline/metrics.json) recalculates actual drawing metrics by executing that commit's original artwork code against its original committed data in an isolated temporary directory. It does not run current code with old version labels. The same review metric measures both baseline and after.

The final after pack was generated once after Gauss's final frozen-source readiness for generic creator-name, song-title and production-place filtering, using art/extractor versions **4/4**. [stats.json](stats.json) records the actual artwork/data source hashes and final review-script hash, including the Python 3.9-compatible text writer. The script checks that source inputs remain unchanged through generation and PNG rendering. It does not build or modify the site's immutable artwork cache.

The previously inspected v3 PNGs, SVGs, statistics, sample IDs and traces are preserved byte-for-byte under [pre-fix-v3/](pre-fix-v3/), with 20 file hashes in [pre-fix-v3/provenance.json](pre-fix-v3/provenance.json). This archive is separate from the original HEAD baseline. The pre-fix observations remain below; they were not erased or relabeled as successful v3 output.

The original 36 IDs and their order are preserved exactly; `sample-ids.json` is byte-identical to the HEAD copy. Cells are numbered left-to-right, top-to-bottom in [sample-trace.json](sample-trace.json). Current family coverage is allowed to change; missing families were not filled by replacing samples.

The [originally independent sample](independent/sample-trace.json) contains the same 36 IDs originally selected by ascending SHA-256 of `spinningtop-artwork-independent-2026-11-26|id`, excluding the fixed 36. Its 2,614 eligible IDs, exclusions, seed, zero overlap and current regression status are recorded in [independent/sampling.json](independent/sampling.json). IDs and order are byte-identical to the preserved v3 sample; all 36 source digests also remain unchanged. No new sample was added and no failing item was replaced. Because the v3 discoveries drove three fixes, the sample is now regression evidence. Final v4 contains 21 abstract, 9 relation, 3 route, 2 city and 1 terrain plate; no stage, portal or still plate, and no empty synopsis. It includes 3 Chinese-text/title rows and 9 remote-image rows. Those gaps are recorded rather than patched by hand. [independent/v3-comparison.json](independent/v3-comparison.json) records before/after results for every original sample position.

The [all-eight-template trace](abstract-templates/sample-trace.json) selects one actual catalogue abstract plate per template, in template order 0–7, using the same separate fixed seed as v3. This existing coverage sheet is separate from the originally independent sample. Its representatives may change when version-dependent template assignment changes; the fixed and independent sample IDs do not.

## Actual SVG measurements

All population figures below use the full 2,650-title catalogue, not just the contact sheets.

| Measurement | Original HEAD | Preserved pre-fix v3 | Final v4 |
| --- | ---: | ---: | ---: |
| Generated / abstract / fallback / error | 1,212 / 1,438 / 0 / 0 | 1,113 / 1,537 / 0 / 0 | 1,102 / 1,548 / 0 / 0 |
| Abstract reasons: insufficient / empty | 1,418 / 20 | 1,517 / 20 | 1,528 / 20 |
| Recipe parameter combinations | 993 | 1,135 | 1,144 |
| Abstract recipe parameter combinations | 96 | 159 | 159 |
| Legacy family/subjects/count/arrangement signatures | 214 | 184 | 182 |
| Unique exact emitted SVG byte strings | 132 | 183 | 181 |
| Unique decolored SVGs, preserving primitive order | 57 | 78 | 79 |
| Unique canonical geometries, safely sorted stroke runs | 55 | 77 | 77 |
| Largest exact-SVG group / catalogue | 179 / 2,650 (6.75%) | 60 / 2,650 (2.26%) | 58 / 2,650 (2.19%) |
| Largest canonical-geometry group / catalogue | 493 / 2,650 (18.60%) | 153 / 2,650 (5.77%) | 148 / 2,650 (5.58%) |
| Abstract canonical geometries | 3 | 16 | 16 |
| Largest abstract geometry group / abstract population | 493 / 1,438 (34.28%) | 104 / 1,537 (6.77%) | 114 / 1,548 (7.36%) |

Parameter counts include fields that may not affect emitted marks, so they must not be used as drawing counts. Eight abstract templates yield sixteen canonical geometries because mirrored coordinates remain distinct; that is not sixteen independently designed templates. The legacy three abstract geometries were mostly small position changes to the same triangle composition.

Maximum duplicate ratio means largest equivalence class divided by the population. It does not mean the total proportion of repeated items. Final canonical duplicate-excess ratio is still **97.09%**: `(2650 - 77) / 2650`. More conservative extraction also increases abstract coverage to **58.42%**. These are limitations, not evidence that the plots were understood. The v4 bump also changes version-derived palette, mirror and abstract-template seeds, so not every v3-to-v4 visual change is a semantic improvement.

The final template distribution for indices 0–7 is **197, 188, 186, 194, 221, 196, 174, 192**. Each contributes about 11.2–14.3% of abstract plates. Each has six exact SVG outputs and two canonical geometries. SVG sizes are 708–5,376 bytes, median 933 bytes, total 3,022,300 bytes.

The recorded final v4 run planned all 2,650 plates in **5.30 seconds**, about **2.00 ms per item**, on Windows/Python 3.14.7. This timer excludes metric calculation, baseline reconstruction and PNG rendering. Other tasks were active, so it is an observed run, not a controlled performance comparison. The archived v3 run was 7.17 seconds; it is not a controlled speed baseline.

Decoloring operates on the **actual emitted SVG**, never a rerendered recipe. It converts painted strokes to one ink and painted fills, including washes, to white; `none`, opacity, width and paint order remain. White wash primitives are retained so they still occlude earlier strokes. The ordered metric preserves primitive order. The canonical metric only sorts contiguous opaque stroke-only runs; filled shapes and other order-sensitive primitives remain barriers. It therefore does not merge a line-behind-wash drawing with a line-in-front-of-wash drawing. Numeric spelling and attribute order are normalized, but equivalent path constructions, reversed line endpoints and mirrored coordinates are not mathematically unified. Unsupported SVG constructs fail explicitly. These hashes are not perceptual similarity or semantic correctness scores.

## PNGs actually inspected

The reviewer previously opened both baseline PNGs and all six v3 PNGs with `view_image`, then separately opened all six final v4 PNGs: fixed, originally independent, and all-template contact/structure pairs. Contact-sheet cells are 180×240 pixels, half the 360×480 source dimensions.

- [Fixed contact sheet](contact-sheet.png) and [fixed structure sheet](structure-sheet.png): the baseline's repeated upright triangle is visibly replaced by stacked frames, circle/rectangle intersections, sparse diagonal shapes, parallel-line density, bridges and terrace lines. Geometry differences survive decoloring. The fixed sheet has 21 abstract plates versus the baseline's 19; several earlier generated motifs now fall back instead of being replaced with another selected musical.
- [Originally independent contact sheet](independent/contact-sheet.png) and [structure sheet](independent/structure-sheet.png): the expanded vocabulary is visible, but repetitions remain easy to spot. Final positions 7, 11 and 25 repeat the upright-triangle composition. Paired people, conflict groups, radial patterns, ships and city skylines recur across unrelated titles. V3 positions 3/4 repeated the triangle and 27/28 repeated the bridge; those historical observations remain visible in the archived v3 sheets. This comparison demonstrates recurring templates rather than universal uniqueness.
- [All eight contact templates](abstract-templates/contact-sheet.png) and [all eight decolored templates](abstract-templates/structure-sheet.png): all eight patterns are visibly distinct. Indices 0–5 occupy row one, and indices 6–7 occupy the first two cells of row two. The remaining blank canvas is intentional. The same double frame, thin strokes and large empty margins still give the whole set a similar visual rhythm.
- The muted gold circles and triangles are faint at half-size on the cream background. Thin radial spokes and parallel lines also lose prominence. Decolored sheets make some accents easier to see. No contrast-ratio or physical-display accessibility claim is made.
- Fixed position 16, *Fame* (`en:3245600`), has visible dancer arms and motion marks, but these intersect the platform edges and make the small drawing busy. The marks remain contained. No cropping, broken image or marks outside the card boundary were seen in the inspected PNGs. This is a visual observation at these raster dimensions, not proof for every viewport or catalogue plate.
- The original baseline structure PNG is preserved as historical evidence. Its old renderer omitted washes; the after structure renderer keeps them white and preserves inherited root styling. Consequently these are not pixel-perfect before/after raster diffs. The recalculated baseline metrics above use the same wash-preserving procedure as the after metrics.

## Pre-fix discoveries and final same-sample regressions

The following v3 visible results were checked against the local merged source text and trace after the independent sample was selected. They were genuine pre-fix discoveries, preserved in [the v3 trace](pre-fix-v3/independent/sample-trace.json) and [the v3 PNG](pre-fix-v3/independent/contact-sheet.png). At the user's request they then drove generic creator/name, song-list and tour/production-context exclusions for v4, with no per-title rules. Consequently the final results below are **post-discovery regressions**, not a fresh blind evaluation.

| Original sample position | Title / ID | Preserved v3 error | Final v4 result actually viewed and traced |
| --- | --- | --- | --- |
| 10 (row 2, column 4) | *Barbarella* / `en:5559219` | Six trees. The `forest` basis came from creator **Jean-Claude Forest**, not a forest setting; the synopsis describes galactic adventures. | Abstract triangle/square/circle composition, `insufficient`, empty basis. The surname no longer supplies a forest. |
| 14 (row 3, column 2) | *Mamma Mia!* / `en:252540` | A figure above two others on a raised block. The `power` basis came from **Queen** in the listed song title *Dancing Queen*, despite the Chinese synopsis describing a search for a father. | Three figures on one baseline, `relation` with a `family` basis from **母亲** in the Chinese synopsis. No power basis or raised block. This does not validate a particular cast interpretation. |
| 32 (row 6, column 2) | *Young Frankenstein* / `en:12084106` | An island. The `island` basis came from **Rhode Island**, a tour-start location, not the fictional setting. | Abstract terrace lines with inverted triangle, `insufficient`, empty basis. The tour place no longer supplies an island. |

All three targeted source-context failures are absent in the final same-ID outputs. This does not establish general semantic accuracy: no new blind sample was added, all 2,650 summaries were not labeled, and no accuracy percentage is inferred. A correct drawn-motif basis can still be grounded in the wrong kind of source evidence outside the bounded exclusions. Famous works remain abstract when their available summary does not provide a reliable motif. The final pass inspected the existing sample and coverage sheets; it did not start another tuning round.

Other known semantic limits from the final semantic review remain: supported explicit people counts are 1–8; the first eligible count is not bound to a narrative role (two observers and five actors can produce two figures); unsupported counts can be skipped; and fictional creator biographies can resemble production biography. The `Actors train daily` case is now a regression fix, not an outstanding failure or independent accuracy evidence.

## Observed checks and scope

- `python scripts/artwork_review.py` completed once for final versions 4/4, with six final PNG renders (fixed, originally independent and all-template pairs). Baseline regeneration used isolated original code; no intermediate artwork library was built.
- Nine direct metric checks passed: color invariance, stroke-order normalization, ordered-SVG distinction, occlusion-order distinction, primitive multiplicity, coordinate changes, retained white fill, numeric normalization and explicit rejection of unsupported structures.
- Original baseline and pre-fix v3 blob hashes, byte-identical fixed and independent IDs/order, independent selection under reversed catalogue order, zero overlap, unchanged sample source digests, all eight template indices, final source/script hashes, template totals and explicit `error: 0` were checked successfully. The three final regression outcomes and non-blind labels were also checked.
- `python -m pytest tests/test_review_metrics.py -q`: **3 passed in 0.38s**, including color/order normalization, preserved fill occlusion and unsupported-shape rejection. The writer uses `Path.open` for Python 3.9 compatibility; no Python 3.9 runtime was exercised here.
- `python -m pytest -q`: **85 passed, 156 subtests passed in 27.46s** after final v4 pack generation in this workspace. This is local regression evidence, not semantic accuracy or remote CI.
- `git -c core.whitespace=cr-at-eol diff --check -- scripts/artwork_review.py docs/artwork-review` passed; Git reported line-ending conversion notices only.

No commits were made by this reviewer. `verification.md`, generator rules, application/UI code, releases and remote CI were outside this review's edits. The `baseline/ui-*.png` files are historical captures. The main task separately refreshed current UI screenshots; this reviewer neither generated nor evaluated those captures. This review does not claim physical-device, browser-zoom, remote cover, or published Pages verification.
