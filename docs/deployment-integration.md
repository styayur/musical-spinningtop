# Portable deployment contract (schema 1)

This public repository is the only application source upstream. A host website may pin an application commit or verified build artifact and mount it; it must not fork the application, artwork, catalogue, sharing or tests into a second implementation. This change does not deploy the personal target or change the existing GitHub Pages site.

## Build and consume

Use a clean checkout of a reviewed full upstream SHA, Python 3.9+ and `requirements.txt`:

```sh
python -m pip install -r requirements.txt
python build_site.py --target github --output dist/github
python build_site.py --target personal --output dist/personal
python scripts/verify_build.py dist/personal --target personal --source-sha <PINNED_40_CHARACTER_SHA>
```

The default remains `python build_site.py` → GitHub target in `_site`. For a source archive without its own Git metadata, supply `--source-sha <PINNED_40_CHARACTER_SHA>` to the build. This is an upstream identity assertion by the caller, not independent proof: verify the downloaded archive against a trusted release checksum first. A source directory nested in the host's Git repository never borrows the host SHA. A normal checkout rejects an explicit mismatching SHA.

Copy **the contents** of the personal output into the host's `spinningtop/` directory, including `404.html`, `LICENSE`, `data/`, `works/`, `static/` and the manifests. Do not wrap it in another `spinningtop/` directory. Keep the complete output together. No Python or database runs on the static host. Building and card generation require no online model, poster, credential or public deployment probe.

Use an app-owned output directory. Builds to the same output serialize; different targets use separate directories. Unknown files or symlinks in an output are rejected and preserved, not deleted. The mount excludes runtime databases, development dependencies, font build inputs, tests, credentials and host `_worker.js`, `_routes.json`, `_headers` files. Incremental builds can retain older public resources and unavailable-work tombstones; use a fresh output for a release inventory. Cache transfer and old asset collection remain future optimizations.

## Configuration and URL contract

`deployment.py` owns the targets, public origin/base path/base URL, work encoding, resource paths and robots policies. The build injects inert JSON plus a base URL into HTML and emits matching `deployment.json`. The same core JavaScript and CSS work on both targets; JavaScript contains no deployment domain constants. Frontend sharing accepts exactly the configured URL for the current stable ID, and only same-origin PNGs in the configured card directory with a 64-hex hash filename and no credentials, query or fragment.

| Target | Public base | Canonical work URL suffix |
| --- | --- | --- |
| github | `https://styayur.github.io/musical-spinningtop/` | `works/<key>.html` (unchanged) |
| personal | `https://styayur.co.uk/spinningtop/` | `works/<key>` |

`key` remains unpadded URL-safe base64 of the stable work ID's UTF-8 bytes. Both builds physically emit `works/<key>.html`. Canonical, OG and X Card metadata, source/year/license text and public HTTPS PNG URLs are written into HTML without requiring JavaScript. Unknown work pages return an unavailable view with `noindex`, never another random work. A successful explicit return to today/explore removes work metadata and restores the app canonical; failed requests preserve the shared identity and URL.

Flask uses the same configuration with `SPINNINGTOP_TARGET=personal` (default `github`), or `create_app(..., deployment_target='personal')`. Local resources remain on the local Flask origin; public candidate URLs use the selected public target, never localhost. `.html`, extensionless and slash work routes are read-only aliases. Bundled works remain **unverified public candidates** without network confirmation; local PNG saving remains available. Sharing does not force an online check.

The existing IndexedDB name and data format are unchanged. Each origin keeps its own history; no cross-domain migration or synchronization is attempted. Moving between domains will not transfer saved days.

## Manifest and integrity

`build-manifest.json` schema 1 records:

- `app_version` (currently `2.1.1-dev`), `source_sha`, `source_dirty` (`null` for source exports).
- Full deployment configuration; catalogue timestamp and exact `site-catalog.json` SHA-256.
- Artwork, extractor and share-card versions (5, 4 and 1, unchanged).
- `files`: relative POSIX paths, byte sizes and SHA-256 for every payload file.
- Payload counts/bytes, full artifact counts/bytes including the manifest, and `inventory_sha256` over canonical compact sorted JSON of `files`.

The manifest excludes its own hash to avoid circularity. `scripts/verify_build.py` checks pinned identity/target, exact inventory, bytes, hashes, totals and configuration; it rejects dirty checkout builds unless explicitly allowed for development. It uses only the Python standard library. Integrity is not authenticity: an integrator must trust/pin the upstream SHA and verify the artifact's external checksum or trusted CI provenance. `build-metrics.json` is diagnostic timing; the manifest is authoritative for inventory totals. Timing and manifest provenance need not be byte-reproducible between independent builds.

## Host routing, CSP and 404 responsibilities

The host owns all route and header configuration; none is emitted into the app mount. Configure and validate these requirements during the later site integration:

1. Redirect `/spinningtop` to `/spinningtop/` before serving the homepage. Serve all app resources below this mount, with correct MIME types.
2. Serve `works/<key>.html` at `works/<key>`; redirect the `.html` and trailing-slash variants to the extensionless canonical URL. Work HTML uses the absolute mount base so resources and exit navigation remain correct through normalization.
3. Serve the app `404.html` with HTTP 404 for unknown app routes. Missing JS/SVG/PNG must retain HTTP 404, never rewrite to the host homepage or an arbitrary work. The host also needs a root `404.html` and must avoid SPA fallback for this mount. Cloudflare documents extensionless HTML redirects and nearest-404 lookup, and otherwise assumes an SPA when the root 404 is absent: [Serving Pages](https://developers.cloudflare.com/pages/configuration/serving-pages/).
4. Scope CSP to the app. Tested policy: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; connect-src 'self'; base-uri 'self'; object-src 'none'`. HTTPS images allow existing explicitly licensed external images; hosts may restrict these origins deliberately. Do not permit arbitrary scripts or relax host-wide policies. Inline executable scripts, social SDKs and third-party tracking are unnecessary. Preserve user-activated download/clipboard/native-share permissions as appropriate; platform links simply open the chosen platform.
5. Valid work and homepage HTML are indexable and canonical to the selected public target; missing works are `noindex`. Staging/preview noindex headers are the host's responsibility. Keep HTML, scripts, catalogues and sharing index coherent on deploy; immutable image filenames may be cached. Old missing image URLs fall back without drawing another work.

Cloudflare's documented limits are 20,000 files on Free and 25 MiB per asset; paid plans support 100,000 files with the documented Wrangler setting. Count the **entire host** plus this app against those limits, not just the app. See [Pages limits](https://developers.cloudflare.com/pages/platform/limits/) (checked 2026-11-27). This task tests a strict local mount and simulated URL normalization, not a Cloudflare deployment.

## Acceptance interface

```sh
python -m unittest discover -s tests -v
python scripts/validate_catalog.py
python -m playwright install chromium
python tests/portable_smoke.py --github dist/github --personal dist/personal
```

The last command compares every actual output file and tests both mount paths, history/offline catalogue use, read-only sharing, normalized aliases, no-JS metadata, exact URL rejection, image fallback and cross-origin storage isolation. Its machine-readable report is `artifacts/portable/comparison.json`. Existing v2.1.0 tests remain active. Verify CI builds both targets and retains comparison/manifests as `portable-deployment-evidence`; no workflow deploys the personal target.

The same successful CI run uploads complete `spinningtop-github-<SHA>` and `spinningtop-personal-<SHA>` artifacts, including `.nojekyll`. Download and extract the chosen artifact, then run the verifier with that exact SHA before mounting. CI artifacts expire under repository retention settings; they are review candidates, not a substitute for a future versioned Release. Alternatively, always rebuild from the pinned source using the commands above.
