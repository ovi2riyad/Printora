# Release checklist

## Studio Photo Maker 3.0 core (2026-11-06)

- [x] Phase 0: inspect source/docs and record the implementation plan.
- [x] Phase 1: persistent selection, improved gallery and balanced framing; test/fix before continuing.
- [x] Phase 2: customers, mobile search, optional imports and photo association; test/fix before continuing.
- [x] Phase 3: immutable orders, history, export recovery and reprint; test/fix before continuing.
- [x] Phase 4: mixed-size sessions, quantities, orientation and retained placements; test/fix before continuing.
- [x] Phase 5: editor tools and print recipes; expanded API/PDF/Qt regression coverage.
- [x] Clean candidate build with required model and preserved older release hashes.
- [x] Final source/frozen acceptance: 29 checks, 68 photos each; promoted separately to StudioPhotoMaker-v3.
- [x] Reviewed source pushed to ovi2riyad/Printora main; hosted Windows CI passed (70 passed, 4 private/local-fixture skips).

Studio-side: physical printer/ruler validation at Actual Size / 100% remains required. Phase 6 tools and the requested Windows installer are included in Printora 3.1; see the current validation record.

## Printora 3.1 tools and installer (2026-11-06)

- [x] Offline reviewed batch finishing with per-item errors and independent durable jobs.
- [x] Numbered contact sheets with explicit customer-field opt-ins.
- [x] Local UUID-only order QR generation/image lookup and optional priced receipts.
- [x] Exact calibration references, stored printer measurements and honest local statistics.
- [x] 81 automated tests pass; source acceptance passes 36 checks with 68 photos.
- [x] Program Files Setup configuration, automatic Desktop/Start menu shortcuts and Installed Apps entry.
- [x] Final installed-app acceptance: 36 checks, 68 photos, bundled model only; install/upgrade/uninstall preservation passed.
- [x] Promote to dist/Printora-3.1; all three previous EXE hashes unchanged.
- [x] Review source for private/generated files and upload to main; hosted results are available in GitHub Actions.

See `PHASE_REPORTS_3_0.md` for each phase's test result and `PROJECT_INFO.md` for current architecture/data rules. Checklists below are historical.

## Professional studio update (2026-11-05)

- [x] Audit active workflows and run baseline: 35 tests passed.
- [x] Flexible exact-size layouts, live quantities, configurable print controls.
- [x] Backward-compatible regional profiles and persistent categorized settings.
- [x] Crop history, previews, library sorting/filtering/deleted recovery.
- [x] Safe backup/restore, referenced-cache protection, rendering improvements.
- [x] New regression tests and isolated studio acceptance: 57 tests; expanded source workflow saved 68 photos and preserved originals.
- [x] Separate standalone build and bundled-only acceptance: 68 photos, all 19 checks passed, exit 0. Previous working release retained.
- [x] Update README / PROJECT_INFO / validation and prepare the reviewed GitHub update.

## Previous release

- [x] Cropper-first dashboard and editable multi-print/perspective regions.
- [x] Automatic tiled-sheet detection and camera EXIF orientation.
- [x] Saved original imports, durable cropped-photo library and permanent serial numbers.
- [x] Library search, rename, saved crop regions and bounded thumbnail loading.
- [x] Portrait, two-source joint and already-combined joint workflows.
- [x] Local background removal followed by canvas-aware framing.
- [x] Direct move/scale/rotate controls, keyboard nudges, snapping, zoom and pan.
- [x] Layer visibility, locking, order, flips and alignment.
- [x] Editable erase/restore strokes and brightness/contrast/color/sharpness.
- [x] Undo/redo, job auto-save/reload and edited-image export.
- [x] Exact-size, inside-border, multi-page A4 PDFs and thin white separators.
- [x] Automated persistence, mouse interaction, processing and PDF checks.
- [x] Full supplied-demo validation, original preservation and restart checks.
- [x] Final clean Windows build and fresh-data packaged acceptance: 68 saved demo photos, processing, PDFs, library restart and original preservation; exit 0.

Studio-side acceptance: print on the intended printer at Actual Size and measure dimensions with a physical ruler. Review hair/edges and source resolution on real orders. Optional future extensions: HEIC/RAW decoders, direct printer-driver integration and in-flight inference cancellation.
