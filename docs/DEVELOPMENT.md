# Development and AI handoff

Printora is an existing Python/PySide6 Windows desktop application. Continue its implementation; do not replace it with a scaffold. The active entry is `main.py` → `app/ui/studio_window.py:StudioWindow`. The retained `main_window.py` and legacy settings still have regression callers.

## Architecture

| Area | Main files |
|---|---|
| Startup/storage | `app/core/database.py`, `migrations.py`, `services/optional_preferences.py` |
| Domain and persistence | `models/domain.py`, `services/customers.py`, `orders.py`, `print_sessions.py` |
| Crop/library | `services/cropping.py`, `ui/cropper.py`, `photo_library.py`, `selection.py` |
| Imaging/composition | `services/imaging.py`, `framing.py`, `selections.py`, `layer_groups.py` |
| Exact printing | `services/layout.py`, `print_geometry.py`, `pdf.py`, `print_transactions.py` |
| Documents/NID | `services/documents.py`, `ui/document_studio.py`, `nid_preview.py` |
| Hardware isolation | `ui/hardware.py`, `hardware_process.py`, `services/hardware.py`, `windows_printing.py`, WIA/TWAIN PowerShell bridges |
| Interface | `ui/shell.py`, `studio_window.py`, `transform_canvas.py`, `panels.py`, `theme.py`, `icons.py` |
| Settings/recipes | `ui/studio_settings.py`, `workflow_settings.py`, `services/preferences.py`, `workflow_preferences.py`, `profiles.py` |
| Protection/backup | `services/export_safety.py`, `recipe_export.py`, `storage.py`, `retention.py`, `record_recovery.py` |
| Release | `app/version.py`, `app/credits.py`, `StudioPhotoMaker.spec`, `scripts/build_release.py`, `installer/Printora.iss` |

## Invariants

- Preserve sources, permanent photo/source/customer/order identities, soft removal, saved jobs and historical snapshots. Never infer serials from editable names or recycle them.
- `Layer.mask` is an RGBA cutout path. Strokes use normalized image coordinates and image-width-relative brush radius. Flips/rotation must map consistently between preview and rendering.
- Layer centers are canvas-normalized. Compute cover-scale before rotation expansion. Placement coordinates are top-left millimetres; PDF converts to bottom-left points using `mm × 72 / 25.4`.
- Preserve nominal photo sizes, inside borders, valid manually moved copies and saved composition settings. A quantity change is not authorization to shrink photos or reframe a document.
- Append compatible dataclass defaults; retain old JSON and order snapshots. Jobs use UPSERT rather than destructive REPLACE of FK-referenced rows.
- GUI-owned main SQLite is not worker-safe. The library connection uses an RLock with cross-thread access enabled. Read settings before workers; copy mutable inputs; update widgets/main database in GUI callbacks.
- Retain document-generation guards around Save/Discard/Cancel, queued scans and worker callbacks. A discarded job must not be saved by a stale callback or revive through undo/navigation.
- Optional preference corruption recovers only affected values and preserves raw rows for diagnosis. Do not reset customer/library/job data as error handling.
- Use shared export guards, explicit file extensions and atomic replacement. Existing ordinary JSON export consent does not authorize overwriting source images, app data or historical artifacts.
- Backups validate required assets as well as manifest hashes, snapshot SQLite/WAL, stage restores, remap paths and preserve the previous data directory. Cleanup must check saved-job/order/session references.
- Print requests must preserve the exact selected printer, fail on invalid geometry and never automatically retry an uncertain submission. Physical output remains unconfirmed until checked by staff.

## Data and models

App data lives under `%LOCALAPPDATA%\StudioPhotoMaker`, independently of `C:\Printora` and Documents working folders. Keep that legacy directory name compatible. The main and library databases use WAL. The application data includes `library`, `cache`, `job_assets`, `document-sessions`, `models` and export-recovery records.

Background model lookup checks configured folder, app-data models, then bundled resources. ONNX Runtime uses local CPU inference. The human portrait model is bundled by the spec; a missing model fails the build. Fast working images cap at 2000 px/edge; Balanced/Fine at 4000. General loading normally caps at 6000. Output limits reject raster exports above 50 MP and transformed buffers above 100 MP rather than changing physical size.

## Test safely

Use Python 3.12 and `requirements-lock.txt`. Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -ra
```

Tests isolate working folders. Private demo/prior-release cases are optional and skip in the cleaned checkout. Preserve those skips as honest coverage limits; do not recreate private fixtures in Git. Synthetic regressions remain self-contained.

Diagnostic CLI runs must use **fresh isolated child-process `LOCALAPPDATA`**, never real studio data. Working folders are redirected inside that disposable directory. Available modes:

| Mode | Required opt-in / inputs |
|---|---|
| `--verify-simple-workflows OUT` | `PRINTORA_SIMPLE_VERIFY=1`; generated images, inert hardware requests, copies/sets/NID/editor/About |
| `--verify-final-studio OUT` | `PRINTORA_FINAL_VERIFY=1`; synthetic documents, layouts, sessions, backup and recovery |
| `--verify-stabilization OUT` | `PRINTORA_STABILIZATION_VERIFY=1`; Save/Discard and invalid optional preferences |
| `--verify-client OUT` | `PRINTORA_CLIENT_VERIFY=1`; panel modes, folders, theme and toolbar |
| `--verify-studio DEMO OUT` | Optional private full studio fixtures supplied externally |
| `--verify-cropper SOURCE OUT` | Multi-print sheet, including generated artwork; crop-to-maker, CPU model and PDF workflow |
| `--verify-visual-scan DEMO OUT` | `PRINTORA_VISUAL_VERIFY=1`; optional private fixtures and pointer/ROI checks |
| `--smoke-test OUT.png` | Startup screenshot only; not end-to-end proof |

`--verify-simple-workflows` can optionally read external `front.jpg`/`back.jpg` through `PRINTORA_NID_VERIFY_DEMO`. Leave it unset for reproducible public checks. Hardware is intercepted in this diagnostic; no physical acquisition or output occurs.

## Build and verify

Build with the normal installed portrait model available; do not point `LOCALAPPDATA` at an empty test folder while packaging. `build.bat` creates the complete payload, copies README/credits/notices/developer and validation guides, then compiles Setup. Frozen acceptance uses fresh data, different cwd, Python-free PATH and no external model override.

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.verify_installer --payload dist/candidate/StudioPhotoMaker --root .tools/FRESH_INSTALLER_CHECK
```

The verifier uses the same installer definition with an isolated test identity/destination. It checks install, shortcuts, registration, upgrade, synthetic installed workflow and uninstall retention without production installation. Stable AppId: `4F077504-7244-4BEB-B290-FE8758932B47`. Fresh production installs default to `C:\Printora`; upgrades retain the selected directory.

## Publication

Keep source in Git and Setup/checksums in GitHub Releases. Never commit private demos, databases, logs, backups, models, generated `build/dist/output`, credentials or local tools. Review actual staged paths and the clean-checkout result. Run Windows CI after pushing and fix failures before marking a release ready. Do not force-push existing history.

Update README for user behavior, this file for architecture, and VALIDATION for executed evidence/limits. Keep version, credits, installer publisher and shipped documentation consistent. Old audits and ad hoc scripts tied to removed demos have been retired; do not cite their local paths as current release evidence.
