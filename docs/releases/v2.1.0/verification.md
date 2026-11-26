# v2.1.0 — A Quiet Stage

Release scope: the cumulative offline imagery, archive compatibility and programme-style UI from PR #23, plus transparent artwork, browser-language invitation, read-only work links and user-initiated sharing from PR #24. No new product feature was added during release closeout.

## Reviewed and merged code

- PR #23 main commit: `ca66e02993a0bcd2823b08149f7e0a6bae9851fb`.
- PR #24 reviewed HEAD: `b694d41fbc481b5b8b0d631fee8c81edda84964d`.
- PR #24 squash merge: `233255014ea073fd05bb65b73bf4c35bb5a9a1ae`.
- [PR Verify](https://github.com/styayur/musical-spinningtop/actions/runs/45846989801), [PR CodeQL](https://github.com/styayur/musical-spinningtop/actions/runs/45846979541) and [PR CodeForge](https://github.com/styayur/musical-spinningtop/actions/runs/45846989963) passed at the reviewed HEAD.
- [Merged-main Verify](https://github.com/styayur/musical-spinningtop/actions/runs/45848655593) and [merged-main CodeQL](https://github.com/styayur/musical-spinningtop/actions/runs/45848655735) passed.

Both active main-branch rulesets were inspected. They require pull requests, the five required CodeForge/browser/Python checks, resolved review threads, squash merging and protection against deletion/non-fast-forward updates. PR #24 was marked ready and merged with an expected-head SHA through the normal GitHub merge API; no bypass or protection change was used. Release documentation is submitted through a separate PR so the accepted PR #24 HEAD remains intact.

## Production evidence

The production checks access `https://styayur.github.io/musical-spinningtop/` directly using Playwright Chromium on Windows. Responses are not intercepted or substituted. Browser viewport/locale settings are simulated, not physical-device validation. The JSON and screenshots in this directory record the completed live checks.

[Pages build and deployment for PR #24](https://github.com/styayur/musical-spinningtop/actions/runs/45849060698) passed at `233255014ea073fd05bb65b73bf4c35bb5a9a1ae`. The post-deployment run passed on 2026-11-26:

- All 2,650 IDs, titles, summaries, years, source fields and the catalogue timestamp match the pre-upgrade production snapshot. Artwork version is now 5. The live sharing index covers all 2,650 IDs.
- Three actual public work pages and their 1200 × 630 PNG URLs returned HTTP 200. No-JS canonical/OG/X metadata, source links, year and CC BY-SA attribution are present. PNG hashes and exact URLs are in [live-results.json](live-results.json).
- Sample SVGs and base.svg have transparent corners and no former external double frame. Live UI screenshots were opened: [Chinese desktop](live-zh-CN.png), [English desktop](live-en-US.png), [no-JS work](live-nojs.png) and [sharing panel](live-share.png).
- zh-CN, zh-TW, en-US and ja-JP invitations/lang attributes passed. The grey circle measures 24 CSS px, with at least 44px click width; observed grey is `rgb(197, 202, 211)`.
- A fresh browser opened and reloaded the same public work, then saved its PNG. Daily and cycle stores remained empty throughout; the sharing panel identifies the work as listed in the actual public index.
- The pre-upgrade browser retained daily `en:4900090` for 2026-11-26 and history `en:61302673` for 2026-11-25. Its full daily/cycle values compare equal before and after the upgrade. These IDs were generated for the controlled release test, not collected from a personal profile.

The history test uses a separate persistent browser profile that genuinely visited the public **pre-upgrade** site and saved two dates before PR #24 was merged. The same profile is reopened against the upgraded site. It is not a copy of the maintainer's personal browser profile. Full IndexedDB daily and cycle records are compared locally; only controlled test IDs and the comparison result are published. Private browser profile/cache data is excluded from Git and release assets.

## Release artifacts and remaining limits

Following v2.0.0, v2.1.0 provides a source ZIP, static-site ZIP and `SHA256SUMS.txt`. The source ZIP comes from the tagged Git tree; the website ZIP comes from the successful Pages artifact for the release commit. Neither includes local SQLite databases, personal histories or browser profiles. The existing tag and Release are never overwritten.

The tag, final documentation-merge SHA, exact-head check links, final deployment and artifact hashes are recorded in the GitHub Release and PR publication record after completion; the report does not substitute previous-commit checks for changed HEADs.

Authenticated social-platform previews/posts, native OS share panels, physical devices, native browser zoom, screen-reader testing and personal existing browser histories remain unverified. The live link/PNG and controlled-history checks do not claim those results. Platform previews remain platform-controlled. Existing heuristic imagery limitations still apply. Cross-build caching and old-resource cleanup remain non-blocking follow-ups. After this release the project enters stable maintenance.
