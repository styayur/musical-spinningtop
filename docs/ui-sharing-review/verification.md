# UI refinement and sharing — 2026-11-26

Base: `ca66e02993a0bcd2823b08149f7e0a6bae9851fb`. Branch: `ui-sharing-refinement`. This is a new patch after PR #23; no change to the draw algorithm, SQLite schema, saved-history migration or imagery extractor. The new PR remains draft for manual review, without merge or deployment.

## Implementation

- The grey information circle is 24 CSS px inside a 44 × 44px button. Existing dialog tabs/focus behavior remains. Artwork width is capped at 18rem instead of 26rem, reducing its maximum height from about 555px to 384px.
- ART_VERSION is 5 and EXTRACTOR_VERSION remains 4. The v5 seed deliberately maps to v4 for palette choice, mirror, detail and abstract-template selection. All 2,650 compositions, people counts and reported bases are unchanged. Only ink, transparency and external framing change. Warm-white strokes, muted gold and 16%-opacity washes replace the ivory canvas and double frame. The generic base migrates under the existing publication lock; versioned SVG URLs stay immutable.
- Stable URL-safe UTF-8 ID encoding produces `works/<encoded-id>.html`. HTML contains canonical, Open Graph and X Card metadata and visible title/synopsis without JS. Public images use absolute HTTPS URLs. Same-origin image URLs serve the exact same PNG for downloading.
- Shared mode boots from embedded, escaped JSON and never calls a draw/details/archive endpoint. Returning to today/exploration requires explicit action. The resolved HTML base is frozen before changing browser history, preserving the GitHub Pages subpath. Unknown/removed links use an unavailable page; stale pages in repeated builds become tombstones and fresh deployments include `404.html`. A local-only ID has no public share link. Flask public pages use the bundled publication merge, not private runtime history or localhost.
- A single share action opens a native HTML dialog. Device sharing appears first when `navigator.canShare` accepts the URL payload. A separate click invokes it, preserving user activation. Platform links, manual copy and PNG download remain available; cancellation is not reported as failure. No SDK, account, key, tracker or automatic publication is added.
- `zh` language variants select Chinese invitation/share strings; other or missing valid language preferences select English. The invitation has the language of its actual text. No work text is translated.

## Share cards and build costs

Cards are 1200 × 630 PNG, with original algorithm art, title, optional year and brand. They contain neither a personal date nor a long synopsis nor an external poster. The bundled Noto Serif CJK font (24,543,080 bytes) is used only by the build/local renderer; it is not copied into the site. Its upstream commit, SHA-256 and SIL Open Font License are under `assets/fonts/`. A full CJK font allows future local entries without a per-catalogue glyph subset or online font request. Unsupported scripts beyond that font's coverage are not certified.

Content-hash names cache cards across builds and deduplicate identical inputs. resvg skips host-font scanning because the generated SVG has no text; Pillow uses the explicit bundled font for text. Ten-card rendering changed from an observed 2.21s to 0.45s after removing host-font scans. The first partial build was interrupted to improve lock scope; it is not claimed as a completed cold-build benchmark. Final measured full builds: cold 404.066s, warm 30.419s; 2,650 PNGs totaling 60,323,997 bytes, clean site 110,285,893 bytes (about 105.18 MiB). Warm site was 110,286,283 bytes after the subpath fix. Later documentation/test changes and a one-line wrapping style do not alter card output. `build-measurements.json` retains raw numbers. Other verification jobs overlapped; these are wall-clock observations on Windows/Python 3.14.7, not controlled cross-machine benchmarks. No meaningless geometry or padding was added to the images.

## Platform endpoint research

Checked 2026-11-26 using official pages and unauthenticated HTTP requests; redirects are preserved in `endpoint-checks.json`.

| Platform | Endpoint and parameters | Observed scope |
| --- | --- | --- |
| X | `https://x.com/intent/tweet?text=…&url=…` | Legacy twitter.com redirects to x.com, then login retaining both parameters. The former developer Web Intent guide now redirects to the general docs; no current guide text was claimed from it. |
| Facebook | `https://www.facebook.com/sharer/sharer.php?u=…` | Redirects to Facebook's own share channel and login retaining the target URL. No application ID is supplied by this app. |
| WhatsApp | `https://wa.me/?text=…` | Redirects to api.whatsapp.com/send retaining the encoded title/link text. No phone number is fixed. |
| Threads | `https://www.threads.com/intent/post?text=…&url=…` | Both parameters match the [official Web Intents reference](https://developers.facebook.com/documentation/threads/threads-web-intents); unauthenticated request reaches login retaining the intent. |

The [Facebook sharing reference](https://developers.facebook.com/documentation/plugins/share-button) describes link/OG preview behavior. The [WhatsApp linking help](https://faq.whatsapp.com/425247423114725) was reachable but had no extractable article body in this environment. Direct endpoint observations supplement, rather than fabricate, unavailable documentation. HTTP reachability and encoded-query checks do not prove authenticated posting or preview rendering. No real social post, native OS share sheet or authenticated platform preview was tested. Sites may cache metadata or render cards differently; saving and manually attaching the PNG is provided.

## Verification evidence

Existing v4 evidence under `docs/artwork-review/` is untouched. `stats.json` compares all 2,650 v5 plans with their v4 composition parameters, verifies transparent SVG corners, preserves the original 36 sample IDs and confirms the downloaded live catalogue's IDs/titles/summaries/year/source fields and snapshot timestamp match the build.

| Executed local command | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 92 passed, 57.885s |
| `python -m pytest -q` | 92 passed and 156 subtests passed, 33.23s |
| `python scripts/validate_catalog.py` | 2,650 catalogue rows / 2,676 source-backed summaries; no data changes |
| `python build_site.py` and fresh/repeated `build(destination)` | Completed full output; cold/warm measurements above |
| `python tests/site_smoke.py` | Passed |
| `python tests/ui_extra_smoke.py` | Passed, including inherited controlled image completion/fallback cases |
| `python tests/browser_smoke.py` | Passed with its self-started isolated Flask runtime |
| `python tests/sharing_smoke.py` | Passed with a strict `/musical-spinningtop/` server rejecting root resources |
| `python tests/sharing_flask_smoke.py` | Passed: real local work page, public link/metadata, identical served PNG bytes and empty daily/seen/last_pick tables |
| `python scripts/ui_sharing_review.py` | Passed: 2,650 generated SVGs; 181 painted variants checked for transparency; 2,650 unchanged composition/basis comparisons |

New unit tests cover ID encoding and rejection, SVG/base migration, composition invariance, long/CJK titles and unknown year, cached PNG generation, HTML escaping/static metadata and read-only Flask routes. Browser tests cover zh-CN/zh-TW/en-US/ja-JP and missing language; daily/random/historical links; fresh-session empty daily/cycle stores; root and strict Pages subpath behavior; no-JS metadata and image reachability; native-share unavailable/cancel/error simulations; copy failure/success; save success/404; focus restoration; and 320/390/768px layouts.

Desktop/mobile screenshots and synthetic CJK/unknown-year plus longest-catalogue-title cards were actually opened and inspected. Warm strokes remain thin and sparse by design. No clipping or missing CJK glyphs was observed in these samples. This is not a new semantic evaluation. Browser layouts are headless Chromium simulated viewports, not physical-device tests. Real browser zoom, screen readers and authenticated preview behavior remain unverified. The new site is not published by this task, so its future public PNG URLs are checked through the locally served equivalent paths, not claimed to be live yet.

## Review status

Local acceptance passes. The PR body records the actual final pushed HEAD and its remote CI results; earlier results are never substituted for a changed HEAD. The full v4 review evidence and catalogue remain unchanged. No production deployment is included. Remaining limitations are platform preview/OS-share/device assurance and the previously documented semantic/visual limits, not claims that simulated posting succeeded.
