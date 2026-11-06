# Studio Photo Maker 3.0 — executed phase reports

The user authorized proceeding through core phases without further approval pauses on 2026-11-06, testing/fixing each phase before continuing, and uploading the finished source to GitHub. Optional Phase 6 extras remain outside core delivery.

## Phase 1 — selection and composition

- Added ID-based persistent selection, blue borders/check overlays, selected serial counts, and a reusable paged library browser with grid/list/thumbnail sizes and date/type filters.
- Improved both prepared-photo pickers and Cropper selection. Added balanced/document/custom framing controls, four physical margins, alignment, framing presets and safe-area overlays. New active auto-framing maps to Balanced; the legacy service path and old saved transforms remain compatible.
- Added a nullable library preparation timestamp and pre-upgrade SQLite snapshot helper. Existing serials and assets are preserved.
- Initial checks exposed a PySide enum access error, which was corrected. New framing assertions now measure visible foreground rather than negligible resampling fringes.
- **Full suite: 60 passed, 2 existing Pillow warnings, 13.62 seconds.** New tests exercise real Qt selection across filters/views, balanced margins/serialization, and library dates/paging. Full source demo acceptance is recorded below when complete.
- Shared library navigation, customer filters and multi-composition routing are integrated with their owning later modules rather than exposing unfinished dashboard destinations.
- Full isolated source demo acceptance passed in **40.58 seconds**, with all **68** prepared photos and the existing **19** workflow checks.

## Phase 2 — customers

- Added customer IDs, optional original/normalized primary and alternate mobiles, name/mobile/ID search, dates, notes, sorting and archive/recovery.
- Added customer profiles, linked library photos/compositions, full Photo Library navigation, customer search, bulk rename/classification/assignment, and optional existing/new customer selection in Cropper.
- Stable source-digest assignments reconcile after crop saving/restart; repeated association is idempotent. Shared mobiles are permitted after a duplicate warning. Imports remain usable without customers.
- Added main-database migration tracking, foreign keys, pre-business-schema snapshot and restored foreign-key validation. New contact/link records are included by the existing SQLite snapshot backup mechanism.
- **Full suite: 62 passed, 2 existing warnings, 17.85 seconds.** Customer tests include Unicode/international/alternate mobiles, duplicates, archive/recovery, stable IDs, existing-photo links, interrupted source-to-crop association and cross-path backup/restore.

## Phase 3 — orders and reprint

- Added immutable customer/composition snapshots, independent order serials, searchable order history/status/date filters, quantities/settings review, print-event history, photo previews and PDF opening.
- Reprint creates a new linked draft. Successful historical PDFs cannot be silently overwritten. A worker-written recovery marker allows startup to finish history recording after a crash between PDF creation and GUI database commit.
- Extended backup/restore and cache references to order snapshots, external successful PDFs and recovery markers. Export attempts use GUI-owned transactions and immutable worker inputs.
- **Full suite: 64 passed, 2 existing warnings, 15.67 seconds** before the additional end-to-end UI test. Added snapshot/reprint, historical mobile search, failed attempt/recovery and restored-order/PDF tests; the UI workflow is checked with the next complete run before Phase 4 starts.
- Final Phase 3 suite including the real mobile-search/order/PDF/reprint UI workflow: **65 passed, 2 existing warnings, 16.02 seconds**.

## Phase 4 — Multi Photo Print

- Added dedicated multi-composition printing, saved-job selection, library preparation with individual review, per-item quantities/presets, duplicate/reorder/remove, session save/reopen and order creation.
- Reused exact physical layout/PDF/preview services; automatic orientation compares both A4 results and preserves orientation on ties. Manual overrides and valid placements persist. Session items have fresh identities and preserve origin settings without modifying source jobs.
- Preview renders only the active page; PDF raw-image caching is bounded. Session data uses one Job payload with normalized session metadata and transactional saves.
- An existing UI test exposed an ambiguous quantity button label in the new module; labels were clarified, preserving existing workflow tests.
- **Full suite: 68 passed, 2 existing warnings, 16.59 seconds.** Tests cover the five-person mixed-size 22-copy example, physical PDFs, fit errors, orientation/ties, quantity/manual-placement retention, session persistence, source preservation and real Qt review/duplicate/reopen behavior.

## Phase 5 — editing, recipes and integration

- Extended country profiles into full page/photo recipes with stable logical IDs, paper orientation, margins/gaps, defaults and JSON compatibility. Explicit application preserves image layers and snapshots the recipe.
- Added brush hardness/opacity with backward-compatible stroke defaults, mask-only preview, background presets/recent colors, layer rename/duplicate, simple group transforms and selected mask/tone reset. Extra controls are collapsible; canvas fitting now resets correctly when switching documents.
- Completed nine-module dashboard navigation with recent customer/order/job selectors and frequent recipes. Historical order PDF protection covers normal UI exports. Customer unlink exclusions survive reconciliation/restart.
- Fixed linked-job updates to use UPSERT, migration DDL rollback, future-schema refusal, restored-connection rebinding, active-page save/undo routing and reprint selection after filtered historical-mobile searches.
- Suite expanded to **74 tests**. Latest recorded run before final source/package checks: **74 passed, 2 existing warnings, 29.72 seconds** while packaging ran concurrently. Source demo acceptance passed **29** checks with **68** photos in **48.26 seconds**; the initial new manual-move fixture was corrected after overlap validation properly rejected its unsafe move.
- Final source/frozen/CI results and release destination are recorded in `VALIDATION.md`. Optional Phase 6 extras remain follow-up work rather than being marked complete.
- Final delivery: **74 tests passed** in **30.38 seconds**. Source/frozen full acceptance each passed **29 checks with 68 photos**, exit 0, in **146.20 / 146.19 seconds** while running concurrently. Clean build exited 0; validated package promoted to `dist/StudioPhotoMaker-v3`; both previous EXE hashes remained unchanged.
- GitHub implementation commit `9e0e3ee` was pushed to `main`. Hosted [Windows run 42165424889](https://github.com/ovi2riyad/Printora/actions/runs/42165424889) succeeded: **70 passed, 4 expected local-fixture skips**, no failures/errors. The promoted EXE's dashboard smoke test also exited 0.
