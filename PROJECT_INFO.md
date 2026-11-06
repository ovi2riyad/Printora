# Printora 3.1 — project information and AI handoff

Last reviewed: **2026-11-06**. This describes implemented source, not a replacement scaffold. Read this file and `README.md`, inspect the active source, and run relevant checks before changing behavior. Executed results are in `PHASE_REPORTS_3_0.md` and `VALIDATION.md`; architecture planning/history is in `DEVELOPMENT_PLAN_3_0.md`.

## 1. Product, authorization and release

Studio Photo Maker is an offline Windows photography workstation: import/crop, numbered library, portrait/joint editing, customers, orders/reprint, mixed-composition A4 printing, recipes and backup. It uses Python 3.12/PySide6 Widgets, SQLite, Pillow/OpenCV, ONNX Runtime CPU and ReportLab. It is not a website and requires no cloud account/server/paid image API. No core 3.0 Python dependency was added.

Repository: [ovi2riyad/Printora](https://github.com/ovi2riyad/Printora), branch `main`. The 3.1 application and installer use the Printora name; existing application-data identity stays StudioPhotoMaker to preserve user work. The user authorized sequential implementation/test/fix/upload, then Phase 6 together with a Program Files installer and automatic shortcuts. This supersedes original planning approval gates.

Release destination after candidate acceptance:

```text
dist/Printora-3.1/StudioPhotoMaker.exe
dist/installers/Printora-3.1.0-Setup.exe
```

Prefer distributing Setup. It installs `Printora.exe` and `_internal` to `{commonpf64}\Printora` (normally `C:\Program Files\Printora`) with all-users Desktop/Start menu shortcuts and an uninstall entry. Installation requires elevation; normal app use does not. For portable distribution keep the entire folder. End users need no Python. v3, v2 and original packages remain preserved. Source checkouts exclude generated packages/models/tools/private photographs. A source push is separate from publishing a binary GitHub Release. See `VALIDATION.md` for executed evidence.

Keep the existing architecture and workflows. Do not rebuild the project from scratch, switch frameworks, move user data to temporary build folders, upload private demos, or use production app data for destructive tests.

## 2. Active UI and navigation

`main.py` imports `StudioWindow` from `app/ui/studio_window.py` as `MainWindow`. `app/ui/main_window.py` is a retained legacy interface used by older regression tests; editing it alone does not change the current app.

`StudioWindow` owns the single-composition editor, workers/timers, save lifecycle and the original stack prefix: dashboard index 0, editor 1, print preview 2, Cropper 3. `StudioManager` extends that window with Orders, Multi Photo Print, Customers and full Photo Library pages, replacing the initial dashboard. Use widget references for added pages; do not hardcode their numeric indices.

The nine dashboard destinations are, in order:

1. Cropper
2. Portrait Maker
3. Joint Photo Maker
4. Multi Photo Print
5. Customers
6. Orders
7. Photo Library
8. Print Recipes
9. Settings & Backup

Recent customer/order/job selectors and frequent-recipe selectors provide shortcuts. Extra mask/layer/background controls are behind **More editing tools**, keeping the editing canvas usable. Shared gallery selection and composition controls are modules, not a second editor/rendering engine.

## 3. Cropper, library and selection

Import JPG/JPEG, PNG, WEBP, BMP and TIF/TIFF; HEIC/RAW decoding is absent. EXIF orientation is respected. Sources are copied into app data and byte-deduplicated with SHA-256. Reimporting a missing stored source repairs its existing record/serial rather than allocating a replacement identity.

Detection first tries face-assisted regular grids for tightly tiled sheets, then contour/content detection. Low-contrast enhancement is detection-only. Regions have four corners and four edge handles; users can move/draw/rotate/preview and undo/redo. Perspective extraction straightens tilted prints. Automatic orientation is a local face-based aid. Sources, current regions and prepared crops persist; crop undo history is session-local and separate per source.

Keep Selected/All saves PNGs plus small JPEG thumbnails. Use Whole Image supports camera portraits and already-combined joint images. Prepared photos have stable UUIDs and permanent serials `#000001`; source serials `S000001` are independent. Removing photos is a soft removal; recovery retains their serials/assets. Never recycle committed serials or delete assets referenced by saved work.

`CropTray(root=...)` is the durable production library. `CropTray()` without a root remains memory-only for older callers/tests, with a total-pixel limit. `PreparedPhoto.image` loads lazily. Dimensions are stored without decoding; thumbnail errors display a Missing placeholder. Missing original assets raise useful errors when actual editing is attempted.

The shared `PhotoLibrary` offers grid/list/size changes, name/serial/type/date filtering and 200-result pages. Queries use `LIMIT/OFFSET`; deep offset paging can be improved if workloads justify it. Photo dates are nullable: old imports are unknown, not guessed from file mtimes. Lightweight available-photo metadata is still retained in `tray.items` for compatibility; full-resolution images are not all decoded at startup.

`PhotoSelectionList` owns a stable `selected_ids` set independent of visible rows. Delegates paint blue selection borders/check overlays; row backgrounds are tinted. Search/view/page changes reapply IDs. Single/joint pickers preserve the one-input or one/two-input restrictions. Select visible means the current page; Clear selection clears off-screen choices too. Do not replace this state with `selectedItems()` for bulk actions that must include hidden selections.

Full library operations include larger preview, prefix-plus-serial bulk rename, bulk classification, customer assignment/unlink and soft removal. Customer-name/mobile search uses main-database relationships; opening Photographs from a customer profile applies a customer filter. Cropper retains its smaller Saved Library sidebar and removed-photo recovery controls.

## 4. Composition, rendering and editor behavior

Defaults: portrait **45 × 55 mm**, joint **55 × 45 mm**, quantity 4, sky blue **#ADD8E6**, enabled gray 0.2 mm inside border. Preferences/selected recipes can override new-job defaults. A joint accepts either one combined photo (keep the people as one layer) or two separate photos (independent layers).

Loading prepared inputs materializes assets if needed, removes backgrounds, then frames them. Active legacy `automatic_framing='auto'` preferences map to the new Balanced path when preparing inputs; old saved transforms are not recalculated on load. `frame_photo(..., 'auto')` remains the legacy bottom-anchored service path for old callers/tests. New active auto-frame controls explicitly request Balanced.

`Photo.composition` stores mode, top/bottom/left/right mm margins, horizontal/vertical fractions, subject scale and optional head/lower-edge anchors. Balanced fits foreground bounds into safe slots with aspect preserved. Document mode optionally uses face boxes for head position; Custom leaves ordinary transforms manual. Combined input stays one group; separate layers get separate slots. Fit/Fill remain alternatives. Named framing presets are stored in config, distinct from page recipes.

Editor controls support move, proportional corner scaling, rotation, numeric transforms, snapping, alignment, flips, visibility/locking, layer order, zoom/pan, tone/edge adjustments and editable Erase/Restore strokes. `Layer.group` is optional group metadata; group transformations update member layers directly. There is no nested rendering hierarchy. Locked members are excluded. Group rotation operates in physical canvas coordinates, not incorrectly in normalized square coordinates.

`Layer.mask` is a path to a background-removed RGBA image, not a grayscale mask. Its alpha is the starting segmentation. Strokes store mode, normalized image points, radius as image-width fraction, optional hardness and opacity. Missing hardness preserves legacy blur behavior; missing opacity means 1. Restore reveals original alpha/pixels, so it can reveal the old background outside the person. Tone/stroke changes do not overwrite source pixels.

Mask-only and original-background comparisons are view options. Positioning marks, selection outlines/handles and safe-area overlays remain absent from all exports. Edited PNG/JPEG exports use the selected background and configured DPI; PNG is not currently a transparent-cutout workflow.

Undo/redo snapshots contain photo, print settings, placements and page count. Cropper has its own dispatch. Global editor undo does not mutate a hidden photo while a management page is active. There is no separate history-panel stack. Auto-save waits about 2.2 seconds of idle editing and postpones while busy. Ctrl+S saves the active single job or multi session.

### Geometry conventions

- Raster size: `round(mm / 25.4 * dpi)`, minimum one pixel; default DPI 300.
- PDF size: exact `mm * 72 / 25.4`, without raster rounding.
- Layer centers are normalized against canvas dimensions and can extend outside the canvas.
- Layer scale multiplies `max(canvas_width/image_width, canvas_height/image_height)` before rotation expands the image. Changing this baseline after rotation changes apparent scale incorrectly.
- `prepare_layer()` applies alpha adjustments/strokes, tone, halo reduction and flips. Stroke coordinate mapping accounts for flips.
- `render_photo()` composites visible transformed layers over the chosen background and does not draw a border.
- `render_bordered_photo()` adds inside raster borders for image export; PDF and current sheet preview use inside vector borders in physical page units.
- Print preview maps raster width AND height independently to exact placement dimensions. Legacy baked-border preview remains available through the default canvas API.
- Raster photo allocations above 50 MP and transformed layer rasters above 100 MP fail before oversized allocation. These are limits, not silent resizes.

## 5. Customers and cross-store relationships

`CustomerStore` owns main-database customer operations. Customers have stable UUIDs plus separate autoincrement display serials `C000001`. Name is required; mobile is optional. Primary/alternative mobile, address/email/notes, created/activity timestamps and archive state persist.

Display phone formatting is retained. Search normalizes Unicode digits/separators without assuming fixed lengths or dropping leading/international digits. Names have normalized search values. Shared phone numbers are allowed; the form warns about probable duplicates instead of imposing a unique-phone constraint or merging records. Archive/recovery does not cascade-delete jobs/photos/orders.

Main tables use enforced foreign keys within `studio.db`. Photo UUIDs/source digests refer to the separate library database; SQLite cannot enforce cross-file foreign keys here. Customer links must be validated at service boundaries. Do not merge the databases merely to simplify this relation.

Optional import assignment writes `customer_source_links` after the source exists. `reconcile(tray)` idempotently creates photo links after cropping/restart, recovering interrupted association steps. Multiple customers can reference identical source bytes without defeating deduplication. Explicit unlinks create `customer_photo_exclusions`, so reconciliation does not undo the operator's choice. Explicit assignment clears the exclusion.

Prepared input UUIDs are saved in `Photo.provenance.library_ids`. Saving/autosaving jobs links their library customers into `customer_job_links`. Jobs with legacy unassigned sources remain usable. Customer profiles display linked photographs, compositions and orders/previous settings.

## 6. Business orders and reprint

`OrderStore` is distinct from editable `Job` saves. Older jobs named “studio order” do not become business orders automatically. Orders have UUIDs and independent serials `O000001`, optional customer FK, immutable customer name/mobile snapshots, dates, notes, status and parent/reprint linkage.

Orders store layout/settings/job metadata in `orders.payload`, while `order_items` holds ordered composition snapshots and authoritative per-item quantities. Snapshot JSON excludes quantity so there is one authoritative value. Reconstruct a renderable Job through `load_job()`. Composition IDs are copied to fresh order-specific IDs, and placements are remapped. Provenance retains origin references. Source/mask assets are referenced and protected by storage scanning; do not delete them because a library tile is hidden.

Only Draft orders can change composition settings/quantities. Ready/Completed/Cancelled histories are preserved. Reprint/duplicate creates a new linked draft from old snapshots, leaving the previous order unchanged. A newly created reprint captures the customer's then-current contact values; the original order retains its historical values.

Statuses: Draft → Processing → Ready on successful PDF generation; failures return to Draft with a Failed event. Completed is an explicit operator action, not proof observed from a printer. Cancelled orders stay in history. Reprint creates a new order rather than reviving a completed/cancelled record.

`begin_export()` commits an attempt and frozen layout before worker dispatch. `write_order_pdf()` atomically writes the PDF and an event/path/checksum recovery marker. `finish_export()` records Ready/Failed on the GUI thread and removes the marker. Startup reconciles pending attempts, verifying the marker and artifact; missing/unverified attempts become retryable failures. A PDF written just before a crash but without a valid marker may remain on disk for manual review.

Normal UI exports reject app-data/original targets and previous successful order PDF paths. New default order filenames use order serials rather than customer phone numbers. Failed destination paths are not treated as success. Missing historical PDFs can be regenerated through reprint if referenced image assets remain available.

## 7. Multi Photo Print and layout

`MultiPhotoPrint` is a separate controller, because the active single editor repeatedly assigns `[self.photo]`. Do not feed multi-item jobs through those callbacks. Session metadata points to its own editable Job; there is no second mutable composition payload. Saved multi jobs/session jobs route to this module.

Adding a saved composition deep-copies settings/layers and allocates a fresh `Photo.id`, retaining origin IDs. Duplicated items also get fresh IDs. Editing a session item opens a separate review job and explicitly returns the reviewed result to that item; it does not overwrite the origin job. Library photos enter a maker/preparation queue and require review before addition.

Per-item quantities, common presets, Apply All, reorder/duplicate/remove, session save/reopen and order creation are implemented. Sessions retain print settings, orientation preference, quantities and placements. Changes save through transactional upserts; `Database.save_job()` must use UPSERT rather than REPLACE because jobs can be referenced by foreign keys.

Layouts reuse `services/layout.py` and PDF/PrintCanvas:

- `auto`: existing centered mixed-size rows.
- `grid_2x2`: fixed centered four-photo blocks.
- `custom`: requested centered rows/columns.
- `max_fit`: full-capacity centered grids.

Grid modes give each composition separate page groups. Automatic orientation evaluates the existing engine once for each A4 orientation, chooses fewer pages and retains current orientation on ties. It is not globally optimal bin packing. Photos themselves are never automatically rotated/distorted/resized. A selected manual paper orientation overrides automatic choice.

`resize_copies()` retains surviving copy IDs/coordinates and finds free slots for new copies. Reopening preview preserves valid placements; explicit Arrange resets them. Appearance/transform edits retain placements; dimensions/layout changes invalidate affected geometry deliberately. The page/quantity summary includes unused printable area, which may be fragmented.

Placements are physical mm from the page's top-left; page/copy indices are zero based. ReportLab converts to its bottom-left origin. Borders stay inside dimensions. Validation checks positive sizes/quantity, exact footprints, copy identity, duplicates/missing copies, bounds/margins and per-page overlap through a vertical sweep.

Studio defaults: 10 mm margins, 0.2 mm gaps. Generic `Job`/legacy defaults still have 2/3 mm gaps; active new workflows override them. 45 mm photos fit four across portrait A4 or six across landscape; 35 mm photos fit five across portrait at the default margins. Never silently shrink to promise five 45 mm copies across a 210 mm page.

Preview renders the active page's compositions at reduced DPI. PDF retains at most four raw ImageReaders in its application cache, but ReportLab's document still needs resources proportional to actual PDF content. Large orders remain a practical memory/time consideration.

## 8. Recipes and preferences

`services/profiles.py` and `ui/profiles.py` implement both existing country profiles and expanded Print Recipes. Keep a single profile/recipe source. Legacy profiles normalize missing fields on read/application; untouched raw stored payloads need not be rewritten.

Recipe fields include logical UUID/version, name/country/kind/usage, physical size, quantity, background/border, preferred PAPER orientation, page margins/gaps, layout/rows/columns and notes. `orientation` derived from photo dimensions is separate from `paper_orientation`. Old profiles receive deterministic logical IDs; rename preserves identity and duplication creates a fresh UUID. JSON import rejects an ID reused under a competing name.

Explicit Apply preserves layers/masks/brushes/transforms, captures the recipe in provenance, and invalidates stale placements. Existing jobs/orders do not track later recipe edits. Default profile/global preference precedence remains compatible: a default profile provides a base, persisted global Photo/Print settings override corresponding values for new jobs, and explicit Apply uses the selected recipe's complete fields. Applying a recipe updates its usage counter for quick access.

Six settings tabs remain General, Photo, Print, Profiles, Processing, Storage. New-job DPI is saved with the job; legacy jobs fall back to 300. Settings changes do not rewrite old jobs. Complex grouping/history UI, full Photoshop/PSD behavior and transparent-cutout export are not implemented.

## 9. Databases, migrations and app-data layout

```text
%LOCALAPPDATA%/StudioPhotoMaker/
  studio.db
  studio-upgrade-snapshots/     Pre-business-upgrade DB snapshot, when needed
  library/
    library.db
    library-upgrade-snapshots/  Pre-3.0 library DB snapshot, when needed
    sources/                   Copied originals named by content hash
    photos/                    Prepared PNGs and .thumb.jpg thumbnails
  cache/                       Segmented RGBA images referenced by jobs/orders
  job_assets/                  Materialized legacy crops
  export-recovery/             In-flight order artifact markers
  models/                      Optional installed models
```

`data_root()` calls interrupted-restore recovery BEFORE mkdir, then creates the directory. Home-directory fallback applies when LOCALAPPDATA is unavailable. Never save user work under `_MEIPASS`, `build` or temporary extraction paths.

Main SQLite WAL tables:

| Table | Contents |
|---|---|
| `jobs` | UUID/name, editable Job JSON, updated timestamp |
| `config` | JSON preferences, framing presets, recent colors/recipe usage |
| `profiles` | Existing name-keyed profile/recipe JSON |
| `exports` | Legacy export paths/dates |
| `schema_migrations` | Applied business-schema versions |
| `customers` | UUID/serial, contacts/search values, activity/archive metadata |
| `customer_photo_links` | Customer FK and logical library-photo UUID |
| `customer_source_links` | Customer FK and logical source content digest |
| `customer_photo_exclusions` | Explicit per-photo opt-outs from source reconciliation |
| `customer_job_links` | Customer/job FKs |
| `orders` | UUID/serial, customer snapshot, lifecycle/layout metadata, reprint parent |
| `order_items` | Order FK, ordered Photo snapshot and quantity |
| `print_events` | Order FK, attempt outcome/path/checksum/dates |
| `print_sessions` | Session UUID, unique Job FK, optional customer FK, dates/name |

Business migration IDs: 1 customers/links; 2 orders/items/events; 3 sessions; 4 unlink exclusions. Each migration uses explicit transactional DDL plus a version record; repeat execution is safe. Version 4 depends on customer tables and may be initialized before 2/3 during service setup. Do not assume only `max(version)` proves every module has initialized. Unsupported future main versions above 4 are refused.

Library tables: `photos(serial AUTOINCREMENT, id UNIQUE, name, source, asset, thumb, width, height, deleted, kind, created_at)`, `sources(serial AUTOINCREMENT, digest UNIQUE, name, asset)`, and `source_regions(asset PRIMARY KEY, payload)`. Current library `user_version=3`; migration is additive/transactional and leaves old dates NULL. Future library versions are refused.

The two DB files cannot form a guaranteed crash-atomic distributed transaction. Cross-store assignment is made recoverable through existing source identity and idempotent reconciliation. Tests use previous-release copies and deliberately failed migrations; no production reset is part of migration.

## 10. Backup, restore and cache safety

`storage.backup_data()` uses SQLite backup snapshots, including committed WAL contents, plus local assets and externally referenced images. Available order PDF artifacts are included and remapped; missing old PDF paths can remain unavailable and require reprint. Models are optional. ZIP creation uses an atomic replacement and SHA-256 manifest.

`JSON_COLUMNS`/`persistent_documents()` enumerate supported persistent JSON containers. `layer_assets()` walks Job/Photo snapshots. Backup, path remapping and cache protection include order items as well as jobs. New asset-bearing fields/tables must extend this mechanism before shipping; backing up raw SQLite bytes alone does not make new external/path-based references portable.

Restore checks exact inventory, safe archive names, hashes, SQLite integrity and main foreign-key references into a sibling staging folder. JSON/path columns, library references, available external PDFs and recovery markers are remapped. If models were omitted, installed models are retained. After confirmation the UI closes workers/timers/connections, retains the old folder as `StudioPhotoMaker.before-restore-...`, swaps in staged data and relaunches. `restore-pending.json` recovery handles interrupted swaps. If installation fails and connections reopen, `StudioManager.rebind()` refreshes every management store against the reopened DB.

`clear_safe_cache()` protects source/mask references from all saved jobs AND order items plus current edits. It removes only old unreferenced direct cache PNG/tmp/download files; it does not clear sources/photos. Corrupt snapshots abort scanning. Do not implement blanket cleanup or discard soft-deleted files.

Backups contain private contacts/photos and are not encrypted. Rollback to an older EXE requires the corresponding complete data backup: backward reading of old jobs by 3.0 does not mean older EXEs can read new optional dataclass fields.

## 11. Image processing and threading

Model lookup: configured directory, app-data models, then packaged/source-root models. Prefer `u2net_human_seg.onnx`, then `u2netp.onnx`; the full portrait model is about 176 MB. Frozen assets use `_MEIPASS` for read-only bundled resources.

Segmentation directly uses ONNX Runtime CPUExecutionProvider; rembg is not imported at runtime. Shared inference session is locked, with four intra-op/one inter-op threads and 320×320 normalized NCHW input. Fast working images cap at 2000 pixels per edge; Balanced/Fine at 4000. General loading caps at 6000 by default. Fine applies local guided matte refinement; optional defringe borrows foreground colors without changing alpha. Quality is source-dependent, not a promise of perfect hair.

Cache keys include source/model paths, modification times and processing quality. Force regenerates a cache result atomically; changed model/quality keys separate results. Face detection is Haar-assisted positioning, not recognition or document compliance.

`Worker(QRunnable)` dispatches expensive image processing; `StudioWindow.run()` manages busy state and GUI-thread callbacks. Workers get copied Job/Photo inputs and captured preferences. Never update widgets or call the main Database connection in a worker. Main SQLite uses normal thread ownership. Library SQLite uses `check_same_thread=False` plus an RLock; preserve both protections.

Active inference has no mid-call cancellation. Closing while busy asks the operator to wait. Use worker dispatch rather than synchronous inference in buttons. Contact data stays local; use synthetic customer fixtures for diagnostics/screenshots, and do not put real contacts in logs, filenames or uploaded artifacts.

## 12. Source map

```text
main.py                         Active entry point and diagnostic CLI
app/core/database.py            Data root, jobs/config/profiles
app/core/migrations.py          SQLite safety snapshots and transactional migrations
app/models/domain.py            Layer/Photo/Placement/Job; compatible defaults
app/services/cropping.py         Durable sources, crop regions, library queries
app/services/imaging.py          Import, segmentation, masks/tone/render/export
app/services/framing.py          Legacy and balanced/document/custom framing
app/services/layer_groups.py     Group transform math on ordinary layers
app/services/layout.py           Physical packing/capacity/validation
app/services/pdf.py              Exact-size PDFs and calibration
app/services/profiles.py         Recipe/profile validation/application
app/services/preferences.py      Active defaults and validation
app/services/customers.py        Customers and cross-store photo associations
app/services/orders.py           Immutable order snapshots/export recovery
app/services/print_sessions.py   Multi-session persistence/orientation comparison
app/services/export_safety.py    Asset and historical PDF target protection
app/services/storage.py          Verified backup/restore/cache references
app/services/studio_diagnostics.py    Base + 3.0 full demo acceptance
app/services/studio_v3_diagnostics.py Customer/session/order/reprint acceptance
app/ui/studio_window.py          Active single-photo editor and application shell
app/ui/studio_manager.py         Nine-module navigation and coordination
app/ui/cropper.py                Crop canvas, region history, legacy-compatible picker
app/ui/photo_library.py          Shared bounded full gallery
app/ui/selection.py              Persistent ID selections and painted overlays
app/ui/composition_controls.py   Margins/anchors/framing presets
app/ui/editor_tools.py           Additional brush/layer/background controls
app/ui/transform_canvas.py       Direct transforms and brush input
app/ui/canvas.py                 Shared/base canvas and physical print preview
app/ui/customers.py              Customer forms and profiles
app/ui/orders.py                 Order review/export/history/reprint
app/ui/multi_photo_print.py      Multi-composition UI and review queue
app/ui/print_options.py          Shared page-layout controls
app/ui/profiles.py               Existing profile manager extended for recipes
app/ui/studio_settings.py        Active six-tab preferences/storage
app/ui/settings.py              Shared legacy model installer/calibration methods
app/ui/main_window.py            Retained earlier interface and regression target
tests/                          Existing and 3.0 API/PDF/Qt regression suites
scripts/                        Model install/development helpers
StudioPhotoMaker.spec            PyInstaller onedir package, required bundled model
setup.bat / run.bat / build.bat  Environment, source launch, candidate build
```

## 13. Development, verification and packaging

Workspace: `D:\Custom Software\Photo Print`. Local runtime: `.tools/python/python.exe`, Python 3.12.10 x64. `.venv` also exists. Do not assume a system python/git/gh or identical installed packages.

```powershell
& '.\.tools\python\python.exe' -m pytest -q
& '.\.tools\python\python.exe' main.py
& '.\.tools\python\python.exe' -m PyInstaller --clean --noconfirm --distpath dist\candidate --workpath build\candidate StudioPhotoMaker.spec
```

On a fresh developer machine use Python 3.12 x64 and `setup.bat`, or a venv with `requirements-lock.txt`. `run.bat` prefers venv Pythonw, then local embedded Pythonw; `build.bat` chooses the corresponding console interpreter. Model installation is separate from pip setup.

The spec fails without `%LOCALAPPDATA%/StudioPhotoMaker/models/u2net_human_seg.onnx`. It collects ONNX CPU libraries/OpenCV data and excludes heavy unused packages/Qt WebEngine. Do not build while LOCALAPPDATA points at an empty acceptance sandbox. Use the normal installed model when building, then test the frozen package with fresh app data and no external model override.

Current expanded local suite contains **81 tests**; see `VALIDATION.md` for final execution/timing. Pre-3.0 baseline was 57. Tests include actual Qt mouse/selection/edit/order/reprint/session workflows, exact PDF placements, customer phones/IDs/archive/associations, immutable histories, migration rollback/future-schema refusal, cache references and cross-path restores. The seven tools tests also cover QR encode/decode, private-field opt-ins, receipt price validation, calibration geometry, batch failures/source preservation, explicit review/save, statistics and installer configuration. CI skips three private-demo cases and one previous-release-copy case when excluded local fixtures are absent. Do not count those as verified demo behavior on CI.

CLI `--verify-studio DEMO_DIR OUT_DIR` exercises old workflows plus 3.0 customer/mixed-session/history/restore/reprint behavior. It creates data/jobs/customers/orders, so **always isolate LOCALAPPDATA**. Example source acceptance in a child PowerShell process:

```powershell
$env:STUDIO_VERIFY_MODEL_DIR = Join-Path $env:LOCALAPPDATA 'StudioPhotoMaker\models'
$env:LOCALAPPDATA = Join-Path (Get-Location) '.tools\new-isolated-source-data'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_QPA_FONTDIR = 'C:\Windows\Fonts'
& '.\.tools\python\python.exe' main.py --verify-studio Demo .tools/new-source-check
```

Use fresh directory names. Environment assignments above should run in a child shell; restore prior values if executing them in a long-lived terminal. For frozen acceptance clear `STUDIO_VERIFY_MODEL_DIR`, preserve fresh data, and launch the candidate EXE with the same CLI arguments. Offscreen Windows screenshots need a font directory for readable text; native Qt Windows does not need that test override.

Other CLI modes: `--smoke-test OUTPUT.png`, older `--verify-cropper SOURCE OUT` and `--verify-runtime SOURCE OUT`. Dashboard screenshots alone do not prove processing. Original demo counts remain 9/11/18 for IMG_0007/8/9, 8/9/9 for portrait sheets and four combined joint inputs: **68** prepared photos. Expanded acceptance now has **36** checks, including the seven studio-tools checks. Diagnostics use synthetic contacts, and evidence/private photographs remain under ignored local folders.

Before promotion: full tests, source acceptance, frozen bundled-only acceptance, visual review, original/source hashes and previous-release EXE hashes. Copy updated README/validation/checklist/attribution/handoff alongside the validated package. No code change appears in the EXE until rebuilt. Update source/docs, review staged private/generated paths, push without force, and inspect hosted Windows CI separately. Do not commit dist, models, databases, backups, .tools, or Demo.

## 14. Remaining practical limits and guidance

- Physical printer/ruler acceptance is outstanding; print at 100% and check driver margins. Saved calibration does not silently alter nominal geometry.
- Source quality, cropping, foreground detection and hair edges require operator review. Government presets do not prove authority compliance.
- No HEIC/RAW, PSD, transparent-cutout export, nested Photoshop groups or independent history panel.
- No interruption inside ONNX calls; no arbitrary-angle nesting optimizer.
- Library links span two databases through stable logical IDs; preserve reconciliation/exclusions and asset-reference scanning when extending them.
- Snapshot paths still depend on assets being available. App-managed sources are retained and backups remap them; external files changed outside the app cannot be assumed unchanged merely because an order's settings are frozen.
- Very large customer/order lists expose bounded recent/search results; deep cursor pagination/advanced phone indexes can be added if real workloads demand it. Lightweight photo metadata remains for compatibility.
- Receipts are simple studio documents, not tax/accounting records. QR lookup requires the matching local order database or restored backup. Contact-sheet cells truncate long labels to prevent overlap. Complex-script font shaping is not guaranteed.

For the next change: inspect the active path, preserve old dataclass defaults/serials/assets, keep GUI/worker ownership intact, extend backups for new references, test against isolated current and previous-release data, and rebuild/validate the actual frozen candidate before release claims. Report executed evidence and limits plainly.

## 15. Phase 6 tools and installer (3.1)

`app/services/studio_tools.py` contains atomic contact-sheet/receipt/QR/calibration exports, strict UUID-only QR parsing, batch preparation and local statistics. `app/ui/studio_tools.py` is reached through the dashboard's Studio tools button. `studio_tools_diagnostics.py` extends the existing acceptance workflow. These reuse existing services and add no Python dependency: OpenCV supplies QR encoding/decoding, ReportLab supplies PDFs, and a locally available Windows font can be embedded without shipping that font file.

Batch inputs are existing durable library assets, up to 200 at once. Each independent worker result contains a Job, preview or error, and explicit reviewed/saved flags. Successful items start unreviewed. Only reviewed items can be saved on the GUI thread; jobs preserve library provenance and customer links. Save results before another batch; unsaved results are memory-only. Makers can reopen saved results for edits, and reviewed saved jobs can be copied to a print session. Processing never modifies source pixels. Worker options include background, quality, framing, recipe and four tone factors; matching recipe kind is required. One combined joint asset remains a single layer.

Contact labels default to serial/photo name; customer names/mobiles require explicit selection. Receipt customer fields and notes also default off; total amount/currency is optional. QR payloads are `printora:order:<32 lowercase hex UUID>`, without names, mobiles, paths or network requests. Image decode runs in the worker; lookup uses GUI-owned OrderStore. Export destinations pass the shared original/app-data/historical-PDF protections. Statistics count generated-order copies once per item despite repeated events, distinguish staff-completed orders, report unknown legacy import dates, and use UTC order months.

Printer measurements are stored in existing JSON config `printer_profiles`, keyed by printer name, with measured width/height and reference X/Y factors. Calibration PDF geometry remains nominal; no silent scaling is introduced. No new database migration is needed for these tools; ordinary jobs/config are already backed up.

`app/version.py` owns version 3.1.0 and shell identity Printora.Desktop. `app/core/windows.py` sets the Windows AppUserModelID and holds a named process-lifetime mutex so Setup detects the running app. Source/frozen application icons use the code-native `assets/printora.svg`, converted to ICO by the build helper. `StudioPhotoMaker.spec` packages that icon and the existing required model.

`build.bat` runs `python -m scripts.build_release`: separate candidate build, required-model check, documentation/icon preparation, then Inno compilation. `--portable-only` skips Setup; `--skip-app --payload PATH` recompiles Setup for an existing complete package. `scripts/setup_installer.py` finds an existing compiler or downloads official Inno Setup 7.1.1 x64 with a pinned SHA-256 into ignored `.tools`; `PRINTORA_ISCC` can override the compiler location. End-user installation/processing needs no Python, compiler, model download or network service.

`installer/Printora.iss` uses stable AppId `4F077504-7244-4BEB-B290-FE8758932B47`, 64-bit Program Files, administrative Setup, automatic common Desktop/Start menu links, Windows Installed Apps registration and normal non-elevated app launching. Setup renames only the installed EXE to Printora.exe; the onedir `_internal` stays adjacent. There is no wildcard UninstallDelete rule and no app-data deletion. Preserve AppId and the existing `%LOCALAPPDATA%\StudioPhotoMaker` location across upgrades.

`scripts/verify_installer.py --payload PATH --root .tools/FRESH_FOLDER` compiles the same script with a separate test AppId, non-admin privileges and isolated app/shortcut paths. It verifies actual install, registration, shortcut targets, upgrade preservation, installed EXE launch, all 36 workflow checks with the bundled model, and uninstall retention. This protects real user data and does not claim a real elevated Program Files install was executed. Production directives are separately checked by the automated suite. Evidence is in `VALIDATION.md`.
