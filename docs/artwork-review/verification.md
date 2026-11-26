# PR #23 final verification — 2026-11-26

Repository branch: `artwork-offline-imagery`. Reviewed input HEAD: `91d44bc3a81c805164376564e7c59547fb2661f6`, with 17 inherited modified files and no initial untracked files. Fetched main remains `e537616f307e87ec7cc57384fbd5d6a2ef053a07`. The inherited diff was preserved outside the repository before editing. No reset, discard, main update, merge, Release, or Pages dispatch was performed.

This report accompanies the final implementation commit. `stats.json` records generator/data source hashes; `performance.json` records frozen experiment source hashes. The PR body records the final remote HEAD and its check results after push. A report cannot contain its own commit hash. Earlier check results do not establish success for the final HEAD.

PR #23 is intentionally a draft: the repository's `native-automerge.yml` automatically enables merging eligible owner PRs. Draft status keeps the requested manual decision boundary without changing that workflow.

## Independent review and corrections

- Flask overwrote archived summaries with empty defaults; removed `/api/details` responses were not marked removed. Saved text now survives both routes, missing archive fields can recover local cached details, and new daily results acquire a minimal text archive. ID-only rows without surviving local data remain unidentified rather than receiving invented text.
- The inherited directory lock was thread-only. Windows byte-range locks and POSIX flock now serialize cooperating processes. Planning remains outside the shared manifest lock; per-input locks coalesce identical work. Manifest publication reloads under lock, preserves concurrent inserts, and cannot revert a newer in-flight publication.
- Base images are initialized under the lock. Atomic replacement retries bounded Windows sharing failures, removes temporary files on exceptions, and recovers abandoned publisher temporary files after process termination. Existing versioned SVG bytes cannot be overwritten. Old SVGs and permanent lock files intentionally remain, so runtime storage grows with revisions.
- Cache hits skip extraction, rendering, SVG reads and publication writes. Rendering exceptions are retryable `error` records, distinct from `empty` and `insufficient`. Final drawing/extractor versions are 4/4, distinct from inherited local version-2 outputs and the intermediate review version 3.
- Reusing an image element allowed an old request event to reach a newer handler. Each drawing generation now gets its own image node. Cover completion after timeout is ignored. Valid-address 404 falls back once; failed base does not loop or draw another musical.
- Title echoes, production boilerplate accumulation, EN/ZH clause negation, biography versus character deaths, numbers in titles/credits/time phrases, and verbal `train` received generic rules. Zero through eight figure counts are checked against actual SVG primitives, including power/conflict/reunion. Selected route subject and displayed evidence follow the painter. Stage dance/death cues now produce distinct marks.
- Current-work information includes safe source links and supplied license/attribution. Tabs implement roving focus, arrows/Home/End and focus return. Daily/free modes have visible icon/button state. Existing restrained programme typography and grey information entry remain.

The synthetic cases in the semantic review methods are regression challenges used during fixes, not a blind accuracy benchmark. Multiple narrative groups and unsupported counts remain heuristic; the first supported affirmative group can differ from the main cast. Metaphors, ambiguous names and fictional creator roles can still be misclassified. No title-specific override was added.

## Local checks actually run

Windows 11 build 26300, Python 3.14.7, Playwright Chromium, isolated generated fixtures and databases:

| Command | Observed result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 85 tests passed, 24.045 s |
| `python -m pytest -q` | 85 tests and 156 subtests passed, 27.80 s |
| `python scripts/validate_catalog.py` | 2,650 catalogue rows, 2,676 source-backed summaries |
| `python build_site.py` | Exit 0 |
| `python tests/site_smoke.py` | Exit 0; IndexedDB full-object migration → removal → original-date lookback, ID-only, refresh, cycles, relative subpaths |
| `python tests/ui_extra_smoke.py` | Exit 0; 18 controlled completion/timeout cases plus actual 404 and base failure |
| `python tests/browser_smoke.py` | Exit 0; self-started temporary runtime, `background=False`, threaded Werkzeug loopback server |
| `python scripts/artwork_review.py` | Complete 2,650-item pack; source hashes checked before/after rendering |
| `python -B scripts/performance_review.py` | 1,875 requests; zero attempted network operations; source/manifest/SVG integrity checks |

An intermediate pytest run during the lock implementation failed on reuse of a generator context manager; the final fresh-lock implementation and complete rerun above supersede it. No assertion or timeout was relaxed. The inherited 30-second Playwright expectation override was removed.

Seventeen controlled concurrency tests cover threads and spawned processes, same/different inputs, changed source/version races, bulk/runtime overlap, interrupted lock holders, transient/permanent replace errors and cache hits. Publication-parity tests build a real static fixture and compare served Flask SVG bytes, including old English details followed by added/changed bundled Chinese summaries.

Image tests hold requests until explicitly released and verify observed event order, then compare the current card/image state. They cover selection and same-ID detail updates, all success/error permutations, and late cover completion after simulated timeout. They do not depend on external-host latency.

Desktop 1440, mobile 320/390 and tablet-width 768 are **Playwright viewports**. 150% zoom is **CSS zoom**. Keyboard tab navigation, focus return, flip, mode state and dialog overflow were exercised. Screenshots here were refreshed; the old images are preserved in `baseline/`. Native browser zoom, screen-reader software, physical phones/tablets and real Wikimedia latency remain unverified. Published Pages was not tested or updated; root/subpath static behavior was tested locally. An offline first visit remains unsupported.

## Full catalogue and visual evidence

| Metric | Reviewed HEAD | Final 4/4 |
| --- | ---: | ---: |
| Completed plans / total | 2650 / 2650 | 2650 / 2650 |
| Explicit rule-evidence plates | 1212 | 1102 |
| Abstract plates | 1438 | 1548 |
| insufficient / empty / error | 1418 / 20 / 0 | 1528 / 20 / 0 |
| Exact emitted SVG byte variants | 132 | 181 |
| Ordered decolored SVG variants | 57 | 79 |
| Canonical geometry variants | 55 | 77 |
| Largest exact duplicate group | 179 (6.75%) | 58 (2.19%) |
| Largest decolored duplicate group | 493 (18.60%) | 148 (5.58%) |

Coverage is 100% generated output, including explicit abstract fallbacks; it is not 100% plot understanding. Final families: abstract 1548, relation 739, city 101, stage 99, route 88, still 31, terrain 29, portal 15. Abstract templates 0–7 contain 197, 188, 186, 194, 221, 196, 174 and 192 works. They yield 48 colored byte variants and 16 decolored geometries, including mirrored/offset variants. The eight base layouts are visually distinct; 16 is not a claim of 16 unrelated visual concepts. The 1144 recipe parameter combinations are separately reported and are not drawing diversity.

The original seed `spinningtop-artwork-sample-2026-11-25` now preserves the original 36 IDs and positions exactly, rather than replacing samples after family classifications change. `independent/` contains a separate seeded 36-work sample excluding those IDs. `abstract-templates/` covers all eight templates using actual catalogue entries. Both agents and the coordinating reviewer opened rendered PNGs, including baseline, colored and decolored sheets. See `visual-review.md` for item-level judgments.

Observed: geometric layout diversity survives color removal; no crop or uncontrolled spill was seen in the sheets. Repeated paired figures and repeated templates remain obvious. Dancer limbs intersect platform outlines; gold secondary strokes are faint at thumbnail size. These are recorded visual limitations. No noise or file-size padding was added. The maximum geometry group is still 148 works, and only 77 geometry classes cover 2650 entries. Rule coverage and geometric diversity are separate from semantic correctness and aesthetic quality.

Independent v3 sampling exposed Forest as a creator surname, Queen inside a song list, and Island inside a tour location. General creator/song-list/production context filters corrected these in v4; the same sample IDs remain. These discoveries are retained in the visual report, and the sample now also serves as regression evidence rather than an untouched blind evaluation.

## Performance

Three isolated rounds; milliseconds, local Flask test-client requests (not HTTP transport). Cold uses a growing manifest; hot prebuilds all 2650 items. Mean is the typical aggregate; P50/P95 use the raw samples in `performance.json`.

| Scenario | n | Mean | P50 | P95 | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Normal cold | 180 | 41.38 | 42.25 | 50.96 | 56.03 |
| Normal hot, full manifest | 180 | 40.52 | 39.42 | 47.81 | 61.86 |
| SQLite writer held 250 ms | 24 | 315.89 | 312.68 | 340.39 | 366.47 |
| Concurrent requests + manifest updates | 240 | 207.39 | 205.67 | 352.70 | 467.38 |
| Concurrent artwork updates | 120 | 337.82 | 310.70 | 550.59 | 641.79 |

Baseline hot mean was 15.58 ms; current with artwork bypassed was 14.92 ms. Paired mean artwork overhead was 25.60 ms. Parsing a full shared JSON manifest adds measurable hot-path work despite skipping extraction/drawing; no multi-second artwork regression was observed. Baseline code was loaded from `git show main`, with original Store methods checked for equality. A separate 5.25-second held writer produced about 5.35 seconds baseline and 5.41 seconds current. SQLite `timeout=15` and `BEGIN IMMEDIATE` were unchanged. This is existing write-lock waiting, not a reason to enlarge browser assertion timeouts.

## Review disposition

Local functional acceptance passes with documented visual/semantic limits. CI at the pushed HEAD must still be checked and recorded in the PR body before recommending merge. The remaining unverified native zoom/device checks limit platform assurance; they are not reported as passes. Retain draft status for the maintainer's review and decision. No deployment authorization is implied.
