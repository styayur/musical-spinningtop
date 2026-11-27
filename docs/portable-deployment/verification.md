# Portable deployment acceptance — 2026-11-27

Baseline: v2.1.0 `8049b902438ea8bd083a2fa2826f9beff9d7ac4e`. Branch: `portable-deployment-v2.1.1`. This is an unreleased portability patch, not a personal-site deployment. The implementation, algorithms, data and tests remain owned by this public repository. No `styayur/site` or Cloudflare resource was accessed or changed.

## Implemented and reviewed

`deployment.py` supplies both targets, stable work IDs, metadata/robots policy and injected resource configuration. GitHub's existing `.html` permalinks remain unchanged; the personal target uses extensionless canonical work URLs while emitting physical HTML files. Work/404 pages use an absolute mount base; the home requires the host's no-slash redirect. Successful exits restore the correct root canonical; failed draws preserve the shared state. The share panel requires the exact current work URL and a same-origin hash PNG in the configured directory. Its prior four platforms, explicit activation and unverified Flask candidate behavior remain.

Builds validate output ownership, serialize only builds to the same output and emit a complete checksum/provenance manifest. A nested source archive cannot falsely acquire a host repository's SHA. The standard-library verifier rejects changed/extra payload files, bad inventory totals, source/target mismatch and dirty source builds (unless explicitly allowed for development). The mount contains no host worker/routing/header configuration. See the [consumer contract](../deployment-integration.md).

No changes to `artwork/`, catalogue data, random selection, SQLite/IndexedDB schemas, CSS layout, v4/v5 visual evidence or `docs/releases/v2.1.0/`. Full-file comparison confirms both targets use identical assets, not merely matching generation parameters.

## Actual dual-target outputs

Local pre-commit builds honestly record `source_dirty: true` and the baseline SHA; these are development evidence, not falsely labeled clean release artifacts. [Build summary](build-summary.json) binds them to the relevant source-file hashes. Verify CI builds and verifies clean PR-HEAD outputs and uploads their manifests/comparison as `portable-deployment-evidence`. The PR body records the final SHA and remote check results separately from this pre-commit evidence.

Complete dual-target CI artifacts are also uploaded as `spinningtop-<target>-<SHA>` for review and later pinned consumption. They are not deployed or published as a Release; retention is limited by the repository's artifact policy.

| Measurement | github | personal |
| --- | ---: | ---: |
| Full artifact files | 7,967 | 7,967 |
| Full artifact bytes, including manifest | 115,417,880 | 115,126,251 |
| Catalogue works | 2,650 | 2,650 |
| SVG files (including base) | 2,651 | 2,651 |
| PNG cards | 2,650 | 2,650 |
| PNG bytes | 60,323,997 | 60,323,997 |
| Largest payload asset | 3,422,440 bytes | 3,422,440 bytes |

Catalogue timestamp remains `2026-09-24T16:36:48.116681+00:00`; both catalogue hashes are `b8ea1e150196f807287a78b34d67bdec0b00bd0632539267e38827e843f7b93d`. Versions remain artwork 5 / extractor 4 / card 1.

[Actual difference list](comparison.json): 2,656 differing files = 2,650 work HTML pages plus home, 404, deployment config, share index, build manifest and timing metrics. All SVGs, PNGs, JS, CSS, catalogue and stable IDs are byte-identical. The personal HTML/JS/CSS/JSON scan finds **zero** occurrences of the former GitHub public origin. Repository source links and historical docs intentionally retain GitHub references.

The build-metrics timer ends before inventory hashing and its incremental `site_bytes` can include an earlier manifest; use `artifact_bytes` above for consumption. Initial parallel builds appeared stalled while producing checksums. An observed `py-spy` stack located the wait in `Path.read_bytes` inside `write_manifest`, not the directory lock; all three processes completed successfully. No timeout was widened and no lock implementation or artwork architecture was changed to hide the I/O wait.

## Executed local checks

Environment: Windows, Python 3.14.7, Playwright Chromium headless. Existing tests use isolated browser contexts or temporary runtime directories.

| Command | Observed result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 99 passed, 35.902 s |
| `python -m pytest -q` | 99 passed + 156 subtests, 46.25 s |
| `python scripts/validate_catalog.py` | 2,650 rows / 2,676 source-backed article records passed |
| `python build_site.py` | Passed; default GitHub target preserved |
| `python build_site.py --target github --output artifacts/portable/github` | Passed |
| `python build_site.py --target personal --output artifacts/portable/personal` | Passed |
| `python scripts/verify_build.py … --source-sha 8049b902438ea8bd083a2fa2826f9beff9d7ac4e --target … --allow-dirty` | Both complete inventories passed (development builds) |
| `python tests/site_smoke.py` | Passed |
| `python tests/ui_extra_smoke.py` | Passed, including controlled image callback/fallback cases |
| `python tests/sharing_smoke.py` | Passed; four locale cases, viewport/keyboard/share failure regressions retained |
| `python tests/sharing_flask_smoke.py` | Passed |
| `python tests/sharing_flask_smoke.py --target personal` | Passed; local/public URL distinction, PNG parity and offline saving retained |
| `python tests/browser_smoke.py` | Passed with a temporary isolated Flask database |
| `python tests/portable_smoke.py --github artifacts/portable/github --personal artifacts/portable/personal` | Both targets passed; full comparison retained |
| Focused deployment tests after verifier path check | 5 passed |
| `git -c core.whitespace=cr-at-eol diff --check` | Passed |

New unit cases cover two targets and metadata, nested-host/source-export provenance, protected output files, inventory tampering, Flask aliases and network-free saving. The portable browser suite uses strict mount servers which reject `/static/` escapes, with a self-script CSP. It checks no-slash home redirects, personal extensionless/`.html`/slash aliases, daily/free/history sharing, unchanged saved records after reload/offline catalogue fallback, fresh receiver no-draw state, controlled failure/retry navigation, unknown work/asset 404s, SVG fallback without redraw, malicious link/image rejection and independent storage on two origins. Two initial test-harness errors (a Playwright callback argument and an evaluate expression returning a function) were corrected before the passing run; no production assertion or timeout was removed.

## Limits and review status

The routing normalization is a **local simulation**, not an actual Cloudflare deployment. Desktop/mobile/tablet sizing and keyboard checks are Playwright tests, not physical-device or native browser-zoom certification. Real authenticated social previews/posting, OS native share panels, physical devices and assistive technology are not newly verified. No release/tag, merge, Pages deployment, main modification, Cloudflare operation or host-site integration is authorized/performed by this patch.

Remote CodeQL initially flagged request-derived filesystem paths and redirect headers in the new loopback test server. The server now uses a fixed route/redirect table constructed from the build inventory; incoming paths only select existing entries. Encoded traversal and response-header injection requests are explicitly rejected in the portable browser test. No alert suppression or security-check weakening was used. This correction changes the regression harness only, not application output.

CodeForge also flagged the two new CLI `print` calls as possible debugging output. Both now serialize their documented machine-readable JSON results directly to standard output. The baseline and regression thresholds remain unchanged.

The host must still validate production routing, CSP, nested/root 404 behavior and its total file budget when integrating. Independent origin histories are intentional. Caching across builds and pruning old public assets remain non-blocking follow-ups. Keep the PR draft for human review; final remote Verify, CodeQL and CodeForge outcomes must be checked at its final HEAD before calling remote acceptance complete.
