# Studio Photo Maker 3.0 — inspection and implementation plan

**Date:** 2026-11-06. **Status:** Implementation authorized for sequential core phases; see `PHASE_REPORTS_3_0.md` for executed results.

**Authorization update:** After Phase 0 the user requested proceeding through core phases automatically, testing/fixing each before the next, then uploading to GitHub. The approval pauses quoted in this original design record are superseded. Current implementation/results are in `PROJECT_INFO.md` and `PHASE_REPORTS_3_0.md`; optional Phase 6 extras remain separate.

This is a plan for upgrading the existing Windows application. Features described as planned below are not implemented. The reviewed source is commit `6407a58d6ca17f1decf6bc3975592767a2a73e8e` on `main` in [ovi2riyad/Printora](https://github.com/ovi2riyad/Printora). The working tree was clean before this inspection.

The attached 3.0 master prompt ends with: **“Start with Phase 0 only. Inspect the repository and produce a detailed, practical implementation plan. Do not modify application code until the inspection and plan are complete and I approve them.”** It also requires approval before each subsequent major phase. This document completes the planning deliverable; it does not authorize implementation of every phase at once.

## 1. Inspection and verified baseline

Reviewed the supplied master request, `PROJECT_INFO.md`, `README.md`, `TODO.md`, `VALIDATION.md`, `GITHUB.md`, the project structure, active entry point/UI, domain objects, SQLite initialization/migrations, crop/library services, framing, image processing, physical layout/PDF pipeline, profiles/preferences, storage, workers, tests, build specification, and Windows CI configuration.

Fresh baseline executed on this workstation:

```powershell
& '.\.tools\python\python.exe' -m pytest -q
```

**Result: 57 passed, 2 warnings, 18.20 seconds.** Both warnings are the existing Pillow `getdata` deprecation in `test_core.py`. This verifies the current source baseline, not any proposed 3.0 feature. No new frozen build, full demo acceptance, physical printer check, or GitHub Actions run was performed during Phase 0.

Existing documented release evidence remains historical: 68 prepared demo photos, 19 expanded workflow checks, and separate source/frozen validation. Current local release: `dist/StudioPhotoMaker-v2`; earlier rollback release: `dist/StudioPhotoMaker`. Neither release needs rebuilding for this planning document.

### What already exists, and what can be reused

| Area | Existing implementation | Upgrade approach |
|---|---|---|
| Application shell | `main.py` loads `StudioWindow` from `app/ui/studio_window.py`; dashboard has three workflows | Extend this shell and navigation incrementally. Keep the legacy `main_window.py` and its regression coverage. |
| Crop preparation | Multi-source import, SHA-256 source deduplication, perspective regions, rotation, EXIF orientation, crop undo/redo | Keep processing and serials. Extend association and browsing rather than create another cropper. |
| Durable library | Separate `library/library.db`, stable photo UUIDs, permanent source/photo serials, thumbnails, soft removal/recovery | Use UUIDs for relationships; display serials to operators. Add metadata and paged browsing without moving existing assets. |
| Portrait/joint editor | One active `Photo`, direct transforms, masks, tone adjustments, undo/redo, local ONNX processing | Improve existing controls and selection. Extract only shared controller helpers needed by new modules. |
| Joint inputs | One combined image or two separate subject layers | Preserve the combined group; frame separate layers individually. |
| Jobs | `Job.photos` already holds multiple compositions, placements, page settings; SQLite saves JSON | Reuse this representation for editable print sessions, with new session metadata. |
| Layout/PDF | Exact mm geometry, mixed-size automatic rows, fixed grids, pagination, placement validation, inside borders, atomic PDF output | Reuse services and `PrintCanvas`; add paper-orientation evaluation and multi-composition UI. |
| Profiles/settings | Country profile CRUD/import/export/defaults; six settings tabs | Evolve profiles into Print Recipes. Keep one source of recipe definitions and existing defaults compatible. |
| Storage | SQLite snapshot backups, checksum manifest, staged path-remapped restore, interrupted-swap recovery, reference-aware cache cleanup | Extend asset discovery and path remapping whenever new persistent records are introduced. |
| Concurrency/build | `QRunnable`, GUI-thread completion signals, CPU ONNX, image limits, candidate onedir build | Preserve these constraints; no new framework, server, GPU requirement, or mandatory online service. |

### Concrete gaps and risks found in source

1. **Framing is deliberately bottom anchored today.** `services/framing.py` sets individual/separate-layer targets around `H * 1.01`; combined inputs use approximately `H * .99`. This explains the reported bottom-heavy result. A regression test explicitly expects bottom contact, so compatibility and the new default need separate coverage.
2. **Library selection is tied to visible widgets.** `Cropper.filter_tray()` clears/rebuilds the list, losing selected rows. `PreparedPicker` retains checkbox IDs for multi-input selection across searches, but the single-photo picker lacks the same persistent selection behavior. Neither has a selected-serial tray or strong visual overlays.
3. **Gallery browsing is bounded but incomplete for large libraries.** `CropTray.query()` limits matches to 200; there is no page cursor. Startup also retains all available lightweight photo metadata for existing callers. Do not confuse lazy full-resolution loading with fully paged metadata access.
4. **The active editor is single-composition.** Its callbacks repeatedly assign `self.job.photos = [self.photo]`. Its sheet renderer renders one photo. Opening a saved multi-photo job currently creates a separate first-photo job. Multi Photo Print therefore needs its own controller, not just another dashboard button.
5. **There are two SQLite databases.** The main database owns jobs/config/profiles/exports; the library database owns photos/sources/regions. SQLite foreign keys cannot enforce relationships between these separate database files. Cross-store references need explicit validation and recoverable write ordering.
6. **There are no customer, business-order, print-event, or dedicated print-session tables.** The older label “studio order” on a `Job` is a name, not an immutable order ledger. Existing jobs must not be silently converted into historical orders.
7. **Stored dates are insufficient for the requested library date filters.** Photos/sources currently have no preparation/import timestamp columns. Historical dates must remain unknown rather than be invented from file modification times.
8. **Backup reference discovery reads only saved jobs.** `storage.referenced_assets()` scans `jobs.payload`; restore rewrites a hardcoded set of JSON/path columns. New order snapshots/session records must be added before those features can be considered safe.
9. **Profiles do not yet hold complete print recipes.** They include size, colors, border, quantity, layout and rows/columns, but not preferred paper orientation or page margins/gaps.
10. **Selection in the canvas is tool dependent.** The layer outline disappears outside the Move tool and when locked. Show the selected layer clearly while still preventing forbidden edits.
11. **Current background workers return tracebacks in error messages.** Customer features must avoid placing contact data into exception text, automatic logs, screenshots, diagnostics, or export filenames.
12. **PDF creation and database history are separate operations.** Order export must distinguish a successfully written PDF from a committed history event, and must recover sensibly if either step fails. Creating a PDF does not prove that a physical print occurred.

## 2. Architecture decisions

### Keep one implementation of each major behavior

- Keep Python/PySide6, SQLite, Pillow/OpenCV, local CPU ONNX, ReportLab, and the current onedir packaging. Core phases should require no additional Python package.
- Keep `StudioWindow` as the application shell. Add focused widgets/controllers for Customers, Orders, a full Photo Library view, and Multi Photo Print. Share the improved library browser between Cropper, selection dialogs, and Photo Library.
- Keep `Photo`/`Layer` as the composition representation and `Job` as the editable print document. PDF/layout services consume those same objects across single and multi-photo workflows.
- Keep prepared library assets separate from edited compositions. A saved cropped photograph has not necessarily been background removed or reviewed. Selecting it for Multi Photo Print must offer preparation/review through the existing editor before treating it as a finished composition.
- Extend current profiles into recipes; do not introduce a second competing recipe database. Framing presets are composition settings, optionally referenced by a recipe; page layout settings remain print settings.
- Extract shared save/export/selection helpers only when reused. Avoid replacing the application with a generic framework or prematurely splitting every small function into a new layer.

### IDs and ownership

| Entity | Stable identity and ownership | Operator-facing identifier |
|---|---|---|
| Imported source | Existing content digest in library database; existing source serial retained | `S000001` |
| Prepared photo | Existing `photos.id` UUID in library database | Existing `#000001`, never recycled |
| Composition/job | Existing `Photo.id` / `Job.id` UUIDs | Job name plus photo serial references |
| Customer | New UUID primary key in main database, separately allocated unique serial | `C000001`, independent of photo serials |
| Business order | New UUID primary key in main database, separately allocated unique serial | `O000001`, independent of customer/photo IDs |
| Print session | New UUID, with a unique reference to its own editable `Job` | Session name/ID |
| Recipe | Existing profile record, with an additive logical UUID in its payload | Editable recipe name; old profile names remain accepted |

Never derive identity from a mutable name, mobile number, list index, asset path, or thumbnail position. Duplicating a composition into another editable session allocates a fresh composition ID and retains provenance separately, preventing placement-key collisions.

### Proposed persistence additions

These are schema responsibilities, not approved/executed DDL. Final columns and migration tests are implemented in the owning phase.

| Table / extension | Purpose and relationships | Phase |
|---|---|---|
| `schema_migrations` | Transactional main-database migration versions/checkpoints; retain existing profile/library migration compatibility | 2 |
| Library timestamp columns | Nullable source import and photo preparation dates; current imports receive UTC timestamps | 1 |
| `customers` | UUID, unique display serial, name, original/canonical mobile fields, optional address/email/notes, created/activity/archive timestamps | 2 |
| `customer_photo_links` | Customer FK plus existing library-photo UUID, unique pair; many photos/people per customer | 2 |
| `customer_source_links` | Customer FK plus source content digest; optional assignment propagated to new crops | 2 |
| `customer_job_links` | Customer/job FKs so saved compositions can be found without inferring them from filenames | 2 |
| `orders` | UUID/serial, optional customer FK, immutable customer contact snapshot, status, dates, notes, frozen print settings/placement metadata | 3 |
| `order_items` | Order FK, position, immutable composition snapshot, quantity, source provenance, optional recipe snapshot | 3 |
| `print_events` | Order FK, unique attempt/event ID, dates, artifact path/hash, result and reprint relationship; preserve previous successful artifacts | 3 |
| `print_sessions` | UUID, unique job FK, optional customer FK, name and timestamps; `Job.photos`/placements remain the single editable document | 4 |
| Profile payload extension | Logical recipe UUID/version, paper orientation, margins/gaps and optional framing-preset reference | 5 |

Use foreign keys for relationships inside `studio.db`, appropriate restrictions on deletion, unique IDs/serials, and indexes on customer search/activity, order date/status/customer, relationship lookups, and session updates. Explicitly enable SQLite foreign-key enforcement on connections that own these tables.

Library references in main-database link tables are **logical cross-store UUID/digest references**, not enforceable SQLite foreign keys. Preserve the two databases and existing paths rather than merge stores merely to obtain foreign keys. Validate cross-store links in services, preserve soft-deleted assets, and report missing links without destroying history. Apply imports/crops to the library first, then idempotently add main-database associations. Keep a small recoverable pending-assignment record for interrupted association work; reapplying a customer/photo pair must not duplicate it. Backups run with application writes paused so their two database snapshots describe one consistent operation boundary.

Orders retain frozen composition values and asset references independently of later job/profile/customer edits. Use normalized rows for searchable relationships and immutable JSON for complex `Photo`/`Layer` snapshots. Define one authoritative quantity per order item; do not maintain independent editable copies of the same quantity in multiple payloads. Session saves must not overwrite origin jobs. Historical snapshots are never automatically reframed or resegmented when reopened.

### Migration and restore policy

1. Inspect schema versions and integrity before migration. Refuse unsupported future schemas rather than guessing.
2. Before the first write of an upgrade, create a recoverable SQLite snapshot of both databases in a separate, dated safety location. Preserve asset files; do not rebuild the library from thumbnails.
3. Apply additive migrations in explicit transactions, recording the version in the same transaction as each change. New dataclass fields are appended with defaults; old JSON remains readable.
4. Where both databases evolve, migrate each store transactionally and record readiness. Startup verifies both before enabling dependent modules. Do not claim distributed atomicity across two WAL databases; interrupted work resumes or reports recovery instructions without creating a new empty library.
5. Preserve photo/source serials, source hashes, crop regions, deletion flags, paths, saved job payloads and customized profiles. Backfill only metadata that can be established reliably. Legacy dates remain nullable with an “Earlier import — date unknown” display.
6. Expand a shared asset-reference walker/path-rewrite registry for jobs, order items/events, sessions and current unsaved documents. Backup, restore and safe cache cleanup must use the same supported record types. Corrupt snapshots fail closed for cleanup.
7. Restore old backups through normal startup migrations. Extend the manifest format only if necessary, preserving supported older archives; add version-specific tests. Include new tables, external assets and new path columns, and verify foreign-key integrity after remapping/migration.
8. Test fresh installs, repeated startup, failed migrations, interrupted association work, and migrations/restores on copies of previous-release databases. Never run these tests against production app data.

### Threading, memory and privacy

- Widgets and the main `Database` connection remain GUI-thread owned. Workers receive immutable copies and captured preferences, not that live connection. Any background database reader owns and closes its own connection.
- Preserve the library lock/connection discipline. Use bounded metadata queries, debounced searches, cached thumbnails, cancellation or generation tokens for stale thumbnail results, and bounded decoded-image caches.
- Gallery selections store IDs and small metadata only. Preview the current print page and cache a bounded number of rendered compositions; avoid rendering an entire order at full resolution merely to open it.
- Preserve current raster-allocation limits, exact mm geometry, alpha/mask semantics and atomic replacement. PDF rendering should release per-composition images when no longer needed; review current caching before large mixed-photo orders.
- Customer contact data remains local. Use synthetic customers for screenshots/tests. Diagnostics/logs omit contact values by default. QR payloads, if later approved, contain only opaque order IDs. Contact sheets and other exports containing customer details require explicit field selection.
- Avoid customer names/mobile numbers in automatic PDF filenames. Keep backup archives private; the existing backup format is not encrypted, and no encryption claim should be made.

## 3. Delivery order and dashboard

Dependency order: **Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → optional Phase 6**. Each phase ends with checks, documentation, a reviewable result, and an approval gate before the next major phase.

The final dashboard order is: **Cropper, Portrait Maker, Joint Photo Maker, Multi Photo Print, Customers, Orders, Photo Library, Print Recipes, Settings & Backup**. Add a consistent icon/navigation system and responsive card spacing in Phase 1, exposing working destinations as they become available. Do not present unfinished modules as operational.

Recently edited jobs are available first; customer/order recents arrive with their modules. Frequently used recipes arrive with recipe usage metadata. Keep dashboard queries bounded and use honest empty/loading/error states. Global navigation must preserve save-before-leave behavior, worker busy state, and keyboard focus.

## 4. Phase 1 — selection, library browsing and balanced composition

**User-visible result:** Selecting photos is obvious and stable, the library is easier to browse, and new automatic compositions have balanced margins instead of mandatory bottom contact. No customer or order system is introduced in this phase.

### Implementation

1. Create one reusable ID-based selection state and gallery presentation. Use strong borders, a check overlay, tinted tiles, visible serials, an accessible focused state, count and a persistent selected-item tray. Highlight selected editor layers independently of whether their handles are editable.
2. Retain selection across search, sorting, scrolling, pagination, thumbnail resizing and switching large-grid/compact-grid/list views. Single-photo and joint pickers use the same state with their existing count restrictions.
3. Define Select All clearly as **Select visible results**, with the count shown; global Clear Selection/Deselect All clears retained hidden selections too. This avoids silently selecting thousands of hidden results. Bulk actions act on the displayed selected count, including off-screen selections.
4. Add adjustable thumbnails, list metadata, a larger preview panel, keyboard navigation, and bounded page navigation/keyset queries. Keep existing serial/name/type/removed filtering, rename/recovery and crop history. Add safe bulk rename preview and bulk classification; customer filters/assignment arrive in Phase 2.
5. Add nullable preparation/import timestamps through a small repeatable library migration. Date filters support known dates and an explicit unknown-date group. Do not alter serials or fabricate dates for old assets.
6. Add versioned composition settings for Balanced, Document and Custom modes: independent margins in mm, horizontal/vertical alignment, optional head/shoulder anchors, and subject scale. Invalid or impossible settings get useful validation rather than silent distortion.
7. Balanced mode fits foreground into the requested safe rectangle with aspect ratio preserved and uses available face bounds to protect heads. Face-assisted Document mode targets configurable head placement; detection failure falls back to foreground bounds. Combined joint subjects stay grouped; separate layers get independent slots/controls.
8. Add reset framing, horizontal/vertical center, top/bottom alignment, equalize margins, numeric transforms, stronger snapping and screen-only safe-area guides. Manual actions update ordinary layer transforms and existing undo history.
9. Store named composition presets in existing local configuration, with validated JSON payloads and stable IDs. Keep them distinct from print recipes; a recipe may reference a framing preset in Phase 5.
10. Use Balanced for new active-workflow framing and explicit new framing actions. Leave saved layer transforms untouched on load. Retain a legacy `auto` service path for compatibility with existing callers/tests that explicitly depend on bottom anchoring; new UI paths must explicitly call the new mode. Existing saved `automatic_framing='auto'` preferences need a documented UI mapping, not automatic rewriting of saved compositions. Keep Fit/Fill available.
11. Establish dashboard/navigation styling and direct Photo Library access using the shared browser. Display recent jobs without changing their content or exposing private data in diagnostics.

### Expected files

- Existing: `app/ui/{studio_window,cropper,transform_canvas,canvas,studio_settings}.py`, `app/services/{cropping,framing,preferences}.py`, `app/models/domain.py`.
- Proposed focused additions: `app/ui/photo_library.py`, `app/ui/selection.py`, and small shared navigation/icon helpers if reuse justifies them. Icons can use Qt/code-native vector assets; no image-generation service is needed.
- Tests: extend cropper/final/guided coverage and add `tests/test_selection_ui.py`, `tests/test_composition.py`.
- Docs: `README.md`, `PROJECT_INFO.md`, `VALIDATION.md`, `TODO.md`, and this plan's status when completed.

### Acceptance

- Real `QTest` clicks, keyboard selection, scrolling and view/filter changes preserve exactly the chosen IDs; check overlay, border, count and serial tray agree. A chosen item outside the visible page remains actionable.
- Large-library tests show bounded queries/thumbnail decoding; no original-image decode occurs just to open or resize a gallery. Old serials and source hashes remain unchanged through restart/migration.
- Synthetic alpha bounds verify all four margins within raster tolerance, correct fallback when no face is found, portrait/landscape canvases, combined groups and separate subjects. Lock/visibility/rotation/flip behavior stays correct.
- Switching new framing controls is undoable and serialized. Old jobs reopen with identical stored transforms. Existing legacy framing tests still pass through the compatibility path; new tests establish the corrected active behavior.
- Editor-only selection/safe-area/pose guides never appear in raster/PDF output. Existing exact-size PDF checks and the full suite pass.
- Run isolated supplied-demo source acceptance for cropping/framing and inspect new gallery/editor screenshots. Build/validate a candidate for the changed active workflow before handing over a distributable; preserve v2.

**Stop for approval before Phase 2.**

## 5. Phase 2 — customers and import association

**User-visible result:** Operators can register/search customers, assign old/new photographs, and find customer photographs/compositions without requiring registration for every import.

### Implementation

- Add migration infrastructure and customer/link repositories in the existing main database. Use archive/recover, not destructive cascade deletion. Add indexes and bounded customer lists.
- Preserve entered mobile formatting alongside normalized search forms. Normalize Unicode digits and separators; retain international prefixes when supplied. Do not assume every number has a fixed length, infer a country without evidence, or truncate leading digits. Search primary/alternative numbers. Handle shared numbers and empty numbers; warn about likely duplicates and offer the existing record without enforcing unique phone numbers or silently merging people.
- Build add/edit/profile/search/sort screens. Profile tabs show linked photos and jobs immediately; order/history sections become functional in Phase 3. Keep customer IDs independent from photo serials.
- Add optional existing/new customer selection during multi-source import. Source deduplication remains content based; importing identical bytes for another customer adds an association instead of changing the original source or dropping the earlier link.
- Link source assignments to crops using stable source identity. Allow bulk assignment/removal of associations for existing photos and optional job assignment. Association changes do not alter pixels, serials, or historical order snapshots.
- Add customer name/mobile/customer filters to the shared library and update activity timestamps on meaningful operations. Archive hides customers from default lists but keeps linked assets/history accessible.
- Extend backup/restore/reference handling in the same phase, including partial-association recovery and cross-store link validation. Add dashboard customer recents using synthetic data in screenshots.

**Expected files:** `core/database.py`, proposed `core/migrations.py`, proposed `models/studio.py`, proposed `services/customers.py`, proposed `ui/customers.py`, shared gallery/import/controller modules, `services/storage.py`, tests and phase docs.

**Acceptance:** CRUD and archive/recovery, empty/international/alternative/mobile search, shared-number duplicate handling, existing/unassigned photos, one customer with multiple people, one source linked to multiple customers, bulk reassignment, restart persistence, migration failure/retry, and cross-path backup/restore all pass. Test a copy of prior-release data; original files/serials/jobs stay unchanged. Run the complete suite and an isolated import/customer workflow.

**Stop for approval before Phase 3.**

## 6. Phase 3 — orders, history and reprint

**User-visible result:** Search a customer's mobile, open an earlier order, review original or changed quantities/settings, and generate a new PDF without repeating cropping and segmentation.

### Implementation

- Add orders, ordered composition items and append-only print-event records. Capture customer name/mobile snapshots when the order is created/finalized; later customer changes cannot rewrite them. Legacy saved jobs stay jobs until the user explicitly creates an order.
- Build searchable order list/detail views, date/status filters, associated composition previews and customer-profile history. Support Draft, Processing, Ready, Completed and Cancelled with explicit transitions. PDF generation moves an order to Ready; Completed remains an operator action rather than a claim of observed physical printing.
- Initially create orders from existing saved portrait/joint compositions using a shared composition selector. Preserve complete layer/settings snapshots and quantities, not just a mutable job ID or flattened preview.
- Duplicate/reprint into a new draft order with a link to its origin. This simplest workflow preserves the old order while allowing quantity/settings changes; every export attempt is separately recorded. Reuse previous processed assets instead of automatically rerunning ONNX.
- Export via the existing PDF service with immutable worker inputs. Track attempts and atomic file output; record PDF success only after verification. Handle cancel/error and PDF-written/history-write-failed recovery without silently recording success twice. Reprints use new default filenames; never silently replace the previous successful PDF.
- Extend asset-reference discovery, backup/restore path rewriting and cache protection for every snapshot/event. Missing legacy assets get a clear repair message rather than replacing a person's photo with another asset.

**Expected files:** `core/{database,migrations}.py`, new studio domain types, proposed `services/orders.py`, proposed `ui/orders.py`, shared composition selection/export helpers, `ui/customers.py`, `ui/studio_window.py`, `services/storage.py`, tests and docs.

**Acceptance:** Order IDs/search/statuses, immutable contact/composition snapshots, linked photos, cancelled exports, failed export/event retry, duplicate/reprint provenance, old settings vs modified copies, soft-removed library assets, customer edits/archive, missing PDFs/assets and restart persistence. Perform the complete mobile-search-to-reprint workflow using real Qt interactions and parse the resulting PDF geometry. Back up and restore orders to another isolated root, then reprint successfully. Run the full suite.

**Stop for approval before Phase 4.**

## 7. Phase 4 — Multi Photo Print

**User-visible result:** Multiple individual/joint compositions with separate quantities and sizes share one reviewed A4 PDF and a reopenable print session.

### Implementation

- Add a dedicated multi-photo controller/widget. Reuse shared library/saved-composition selection, `Job.photos`, `PrintOptions`, `PrintCanvas`, `auto_layout()`, `resize_copies()`, `validate_layout()` and `export_pdf()`.
- Copy finished composition snapshots into the session with fresh IDs and origin references. Raw prepared library photos enter an explicit prepare/review step through the existing portrait/joint editor. Canceling that step does not add an unfinished item. An editor return callback updates only the chosen session item.
- Provide per-item quantity presets/numeric entry, Apply to All, remove/reorder/duplicate/clear, and counts for compositions/copies/pages. Appearance, size, border and background remain per composition; page margins/gaps/orientation belong to the session. Explain conflicts when an item came from a recipe with different page preferences.
- Default mixed-size sessions to Automatic rows. Existing 2×2/custom/max-fit modes group each composition onto its own pages; retain and label that behavior instead of promising a mixed-grid optimizer. A future compact nesting algorithm is not required to meet this phase.
- Compare the existing layout engine on portrait and landscape A4. Prefer fewer pages; retain current orientation on ties for stability. Explain which candidate fits when one fails. This optimizes between those two engine results, not every mathematically possible arrangement. Never rotate/rescale actual photographs to force a fit.
- Automatic orientation/reflow runs when explicitly arranging a new or changed sheet. Reopening preview and ordinary edits preserve valid manual placements. Changing margins, page orientation or dimensions explicitly invalidates/rebuilds incompatible layout, with an appropriate review prompt if manual work would be lost.
- Show every page interactively, unused printable area and fit warnings. Compute area from the printable rectangle and exact image footprints; explain that leftover area can be fragmented and does not guarantee another photo will fit.
- Save session metadata plus its own editable Job atomically in `studio.db`. Reopen restores all selected snapshots, quantities, layout settings and placements. Route multi-photo saved jobs to this module instead of the single-editor first-photo fallback. Export can create/attach a business order through Phase 3 services.

**Expected files:** proposed `ui/multi_photo_print.py`, proposed `services/print_sessions.py`, `core/{database,migrations}.py`, `models/domain.py` for additive provenance only if needed, `services/{layout,pdf,storage}.py`, `ui/{studio_window,print_options,canvas}.py`, shared selectors/export helpers, tests and docs.

**Acceptance:** Use the requested 4/8/2/4 mixed portrait/joint quantities plus a fifth person in an end-to-end example. Verify totals, exact sizes, individual borders, both paper candidates, tie behavior, manual override, multi-page output, missing/duplicate-copy rejection, fresh IDs on duplicate, source-job hash preservation, manual placement retention and full session reopen. Test save failures without half-saved sessions. Reprint a restored mixed-photo order. Bound preview/export memory for many distinct compositions; run full regression and isolated demo acceptance.

**Stop for approval before Phase 5.**

## 8. Phase 5 — advanced editing and Print Recipes

**User-visible result:** Faster common finishing operations, better mask controls, and one reusable recipe system covering both photo and page settings.

### Implementation

- Extend the existing profile manager/payloads with recipe ID/version, preferred paper orientation, margins/gaps, quantity, dimensions, background/border, layout and rows/columns. Preserve country labels, old JSON import, customized presets, starter restoration and explicit Apply behavior.
- Make preset/default precedence visible: existing saved jobs keep their values; existing global preferences remain compatible; explicitly applying a recipe uses its defined values. Changing a recipe/default does not mutate saved jobs or historical orders. Maintain logical recipe IDs across rename and new IDs on duplicate.
- Add background presets (sky blue, white, light gray, dark gray, red), recent/custom colors, reset and comparison using the existing render path.
- Extend saved mask strokes with hardness/opacity defaults that reproduce old strokes. Add mask-only preview, clear brush/zoom feedback and existing edge refinement controls. Keep alpha/tone operations shared by preview and export.
- Add layer rename/duplicate, clear selected adjustments, stronger ordering controls and keyboard shortcuts. For practical grouping, store group metadata and transform the member layers together with one undo checkpoint; do not introduce a separate nested rendering tree. Defer complex nested groups if they threaten consistent export behavior, and state that limit explicitly.
- If useful, expose the existing undo stack as a history view with action labels. Do not maintain a second history mechanism. All new edits participate in the existing save/undo lifecycle.
- Finish dashboard recipe access/frequently used recipes and consistent navigation across all nine destinations.

**Expected files:** `services/{profiles,preferences,imaging}.py`, `ui/{profiles,studio_settings,studio_window,transform_canvas}.py`, shared editor helpers, `models/domain.py`, migration/storage handlers if payload references change, tests and docs. No additional core dependency expected.

**Acceptance:** Legacy recipe/stroke/job migration; recipe CRUD/defaults/rename/import/export; explicit application preserves layers and resets only affected placements; opacity/hardness/erase/restore at different zoom/flip/rotation; layer duplication/groups/history; original-image preservation; preview/raster/PDF consistency and overlay exclusion. Run full tests, source acceptance and candidate/frozen acceptance before release promotion.

**Stop for approval before optional Phase 6.**

## 9. Optional Phase 6 — choose extras after the core is stable

These features are separate optional deliverables, not prerequisites for finishing Phases 1–5. Confirm the selected subset before implementing it.

| Feature | Reuse / scope | Extra checks or dependency decisions |
|---|---|---|
| Contact sheets | Shared library selector and ReportLab thumbnail grid; serial/name by default | Customer name/mobile are explicit opt-ins; pagination, readable labels, missing thumbnails |
| QR order lookup | Encode opaque local order ID and support app/scanner text lookup | Only add a small licensed offline QR encoder if selected; no contact data or web URL dependency |
| Receipts | Order snapshots and ReportLab; optional simple price fields | No accounting subsystem; handle Unicode names with an appropriately licensed bundled font if required |
| Batch finishing | Existing background/framing/tone workers applied to copies | Per-item review, bounded queues, progress, failure isolation, original preservation |
| Calibration | Extend existing PDF calibration with both rulers/reference boxes | Per-printer preferences; exact nominal PDFs remain unchanged; physical ruler acceptance still required |
| Local statistics | Indexed aggregate queries on customers/photos/orders/events | Distinguish generated copies from operator-confirmed printing; no fabricated historical counts or financial reporting |

## 10. Verification and release gates

For each implementation phase:

1. Inspect affected paths again and state the concrete files/scope before editing. Use small reviewable commits; keep unrelated work out.
2. Run targeted tests for new behavior, then the full suite. Existing compatibility tests remain passing. Use temporary `LOCALAPPDATA` and synthetic customers; restore environment overrides afterward.
3. Verify migrations on disposable fresh/legacy/prior-release copies, repeated startup, and relevant failure recovery. Include asset/serial/source-hash comparisons.
4. Run isolated full demo acceptance for image/persistence/print changes, extend `studio_diagnostics.py` for each new actual workflow, and visually inspect representative renders/screenshots. Preserve the baseline crop counts unless an intentionally reviewed detection change warrants otherwise.
5. Build a separate candidate when handing over changed executable behavior. Validate its actual workflows with fresh data, no external model override and only bundled dependencies. Keep `dist/StudioPhotoMaker-v2` and the older release intact until a separately named candidate is verified and promoted.
6. Update `README.md`, `PROJECT_INFO.md`, `VALIDATION.md`, `TODO.md`; update `THIRD_PARTY.md`, build instructions and `GITHUB.md` when relevant. Report exact executed results separately from earlier evidence and planned work.
7. Review staged paths/diffs for private photographs, customer data, database files, output artifacts and credentials before any GitHub upload. A source push is distinct from publishing a packaged release asset. Do not tag or publish a “3.0 complete” release while core phases remain unfinished.
8. Report completed behavior, evidence and limits; wait for approval before starting the next major phase. No unresolved critical regression may be carried into the next phase.

Final core acceptance must exercise: optional customer registration → multi-source import → crop/library persistence → portrait/combined/separate-joint preparation → manual corrections → multi-photo selection and per-person copies → exact optimized A4 PDF → saved order → restart → mobile search → reprint from historical snapshots → cross-path backup/restore → repeat reprint. Run this through both source and frozen application. Physical printer/ruler testing remains a separate studio-side requirement.

## 11. Phase 0 outcome and next action

- Inspection and practical architecture plan: complete.
- Fresh source baseline: **57 tests passed**; two existing warnings.
- Application code, production databases, releases and repository history: unchanged by this phase.
- Only new deliverable: this planning document. No 3.0 implementation, migration, EXE build, release promotion or GitHub push has been performed.
- Next authorized step, **after user approval**, is Phase 1 only: selection visibility/persistence, shared library browsing, balanced framing/composition controls and the initial navigation polish, followed by tests, acceptance and updated documentation.

Approval of Phase 1 does not authorize skipping the later phase review gates. Detailed later schemas remain proposals to verify against the code and the completed preceding phases.
