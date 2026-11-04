# Studio Photo Maker — project information and AI handoff

Last reviewed: **2026-11-05**. This file describes the implementation in this workspace, rather than a proposed application. Read it before changing the project, then inspect the relevant source files. Update it when behavior or architecture changes.

## 1. Purpose and current state

Studio Photo Maker is a local Windows desktop application for a small photography/printing studio. It prepares images from scans or camera photographs, keeps a numbered photo library, makes individual or joint portraits, and exports physically accurate A4 print sheets as PDF.

GitHub repository: [ovi2riyad/Printora](https://github.com/ovi2riyad/Printora), branch `main`. The repository name does not currently change the displayed application name. See `GITHUB.md` for source/release publishing and clean-clone instructions.

The application is implemented in **Python with PySide6/Qt Widgets**. It is not a website and does not require a server, browser, account, or cloud image service. Background removal runs locally using an ONNX portrait segmentation model. An optional model installer needs an internet connection; normal processing with the bundled model works offline.

The current standalone release is:

```text
dist/StudioPhotoMaker/StudioPhotoMaker.exe
```

Distribute the **whole `dist/StudioPhotoMaker` folder**, including `_internal`. End users do not need to install Python. Developers running the source do need a Python runtime and the dependencies.

The project has already been implemented, tested, packaged, and exercised against the supplied demo images. Continue from the existing code. Do not replace it with a new scaffold or assume that the original feature request is still unimplemented.

## 2. User intent and decisions to preserve

The user asked for a simple studio workflow with three dashboard options, in this order:

1. **Cropper**: import a source, extract one or many photographs, and keep them in a reusable library.
2. **Portrait print**: choose a prepared photo, compose a portrait, and print copies.
3. **Joint photo print**: choose two individual photos or one already-combined couple photo, compose the result, and print copies.

The original idea used a temporary memory tray. The later requirement explicitly changed this: **imported sources, prepared photos, serial numbers, and crop regions now persist across restarts**. Do not revert to clearing the library on exit.

Other established requirements:

- Assign default serial numbers automatically so staff can identify and find images.
- Accept scans containing multiple printed photographs, including tightly tiled sheets and rotated or tilted prints.
- Accept ordinary supported mobile-camera images and respect EXIF orientation.
- After crop preparation, remove the background when a photo is loaded into a maker, and frame the subject to its canvas automatically.
- Provide manual correction when automatic detection or positioning fails.
- Default portrait size: **45 × 55 mm**, editable. Default joint size: **55 × 45 mm**, editable.
- Default replacement background: sky blue **`#ADD8E6`**.
- Provide portrait positioning marks in both makers. These marks belong to the editing view and must not appear in the final image/PDF.
- Offer practical Photoshop-style controls: direct movement, scaling, rotation, layers, mask correction, tone adjustments, and undo/redo.
- Let staff choose border thickness/color and quantity, then preview/export a PDF.
- Keep copies close together with a small white separator, without silently shrinking the requested physical photo size.

The user gave freedom to improve usability and finish the application. That does not imply that every Photoshop feature is required. Preserve the straightforward studio workflow.

## 3. Main workflows

### Cropper and durable library

Import supports JPG/JPEG, PNG, WEBP, BMP, and TIF/TIFF. Ctrl+O and drag-and-drop route to Cropper in the active interface. HEIC and RAW decoding are not implemented.

Imported sources are copied into application data. Byte-identical imports are deduplicated using SHA-256 and receive source serials displayed as `S000001`. The original external source is not edited.

Crop detection first attempts a regular face-based grid for tightly tiled passport sheets, then falls back to contour/content detection for separate printed photographs. Each region has four editable points. Staff can move regions, drag corners, draw additional regions, and rotate extracted crops. Perspective transformation straightens tilted prints. A local face detector attempts to orient portraits upright.

**Use Whole Image** handles an individual camera portrait or a photo that already contains both joint subjects. **Keep Selected Crop** and **Keep All Crops** save prepared images as PNG files plus small thumbnails. Each prepared photo receives a permanent serial displayed as `#000001`.

The saved library supports search, rename, and removal from the visible gallery. Removal is a soft delete: underlying assets are retained because saved jobs may still reference them. Persisted photo serials are not recycled. The gallery displays up to 200 recent matching entries; searching can find older ones. Full images load lazily rather than all being decoded at startup.

### Portrait and joint composition

Portrait selection requires one prepared photo. Joint selection accepts one or two:

- One input means an existing combined joint photograph. Keep both people together in one layer.
- Two inputs mean separate subjects, each with an independently editable layer.

The picker uses checkboxes, and checked selections survive changes to the search text. Labels carry the photo serial so the same source can be identified later.

Selected prepared assets are materialized if necessary, backgrounds are removed, then canvas-aware framing runs. Automatic framing uses foreground bounds and optional face boxes to place heads and shoulders, bring clothing to the lower edge, and fit a combined group without splitting it.

**Auto Frame**, **Fit Photo**, and **Fill Canvas** provide alternative starting positions. Automatic face detection is a positioning aid, not identity recognition or proof of document-photo compliance.

### Editing and saving

The editor has Transform, Finish, and Print controls. It supports direct layer dragging, proportional corner scaling, a rotation handle, numeric transforms, center snapping, keyboard nudges, view zoom/pan, flips, visibility, locking, layer order, bottom alignment, and head-size matching.

Finish controls include brightness, contrast, saturation, sharpness, mask contraction/expansion, softness, and editable Erase/Restore strokes. Strokes and adjustments are stored as settings; they do not overwrite source pixels. Restore reveals the original source alpha/pixels, so painting beyond the subject can reveal the old background.

Undo/redo uses photo-state snapshots. Jobs auto-save after approximately **2.2 seconds** of idle editing, with explicit Save Job and Saved Jobs controls also available. Auto-save postpones while a worker is busy. Saved jobs restore editing settings and existing print placements.

Edited-image export writes PNG or JPEG at 300 DPI with the configured border. The Before/Original Background comparison is a view option, not an instruction to export the unprocessed source. Final rendered photos have their selected background; PNG export is not currently a transparent-cutout export workflow.

### Print sheets and PDF

Copies are placed on portrait or landscape A4. The active studio workflow uses **10 mm margins** and **0.2 mm horizontal and vertical gaps**. Blank page space creates the thin white separators.

At 45 mm width, four copies fit across portrait A4 and six across landscape A4. Five 45 mm photos require at least 225 mm before margins/gaps, so they cannot fit across a 210 mm portrait page at full size. At 35 mm width, five fit across portrait A4 with the current margins. Never resize photos silently to satisfy a requested row count.

Auto layout centers rows, supports quantities and additional pages, and keeps nominal dimensions. Staff can move placements in preview; validation checks bounds, overlaps, missing copies, duplicate copies, and stale dimensions before export. Existing valid placements should be reused rather than regenerated merely by reopening preview.

PDF geometry uses exact millimetres converted to points. Photo borders are drawn inside the footprint. Print PDFs at **Actual Size / 100%**. A physical printer/ruler check remains necessary; no physical printer was available during development validation.

## 4. Architecture and file map

```text
main.py                         Application entry point and diagnostic CLI modes
app/
  core/database.py              App-data path, jobs/settings/profiles/export database
  models/domain.py              Layer, Photo, Placement, Job dataclasses
  services/
    cropping.py                 Sources, crop regions, durable library, extraction
    imaging.py                  Import, ONNX inference, layer preparation, rendering
    framing.py                  Face-assisted canvas framing and joint alignment
    layout.py                   Physical page geometry, packing, validation
    pdf.py                      ReportLab photo PDFs and calibration sheet
    studio_diagnostics.py       Current full demo acceptance workflow
    cropper_diagnostics.py      Earlier cropper-focused diagnostic
    diagnostics.py              Earlier runtime diagnostic
  ui/
    studio_window.py            ACTIVE dashboard and studio workflow controller
    cropper.py                  CropCanvas, Cropper widget, PreparedPicker
    transform_canvas.py         ACTIVE Photoshop-style editing canvas
    canvas.py                   Shared/base editor and print-preview canvas
    workers.py                  QRunnable worker and result/error signals
    settings.py                 Preferences, model installation, calibration
    profiles.py                 Profile management UI
    main_window.py              Earlier advanced interface, retained in repository
tests/                          Unit, integration, PDF, and Qt mouse-interaction tests
Demo/                           User-supplied private demo photographs
scripts/                        Supporting development/validation scripts
assets/                         Asset directory
requirements.txt                Allowed dependency version ranges
requirements-lock.txt           Exact versions recorded for tested environment
setup.bat                       Create a standard .venv and install requirements
run.bat                         Run source with .venv or local embedded Python
build.bat                       Package using .venv or local embedded Python
StudioPhotoMaker.spec           PyInstaller onedir build specification
README.md                       User/developer quick guide
VALIDATION.md                   Recorded test and release acceptance results
TODO.md                         Release checklist and remaining studio-side checks
THIRD_PARTY.md                  Dependency/model attribution
GITHUB.md                       GitHub upload, fresh-clone, CI, and release guide
.github/workflows/tests.yml     Windows headless tests on pushes and pull requests
.tools/                         Local runtime, logs, diagnostics, development outputs
build/                          Generated PyInstaller build files
dist/StudioPhotoMaker/          Generated standalone Windows application folder
```

**Entry-point distinction:** `main.py` imports `StudioWindow` from `app/ui/studio_window.py` as `MainWindow`. Editing `app/ui/main_window.py` alone will not change the current app's main interface. The old interface remains relevant to some regression tests and shared code, so do not delete it casually.

## 5. Data model and coordinate conventions

### Domain objects

`Layer` stores source and processed-image paths, normalized center `x/y`, relative scale, rotation, erosion, feather, label, visibility, lock state, flips, four tone factors, and mask strokes. Default center is `(0.5, 0.5)` and default tone factors are `1.0`.

The field named **`mask` is a path to a background-removed RGBA image**, not just a grayscale mask. Its alpha is the initial segmentation mask. If absent, preparation uses the source image.

`Photo` stores its ID, name, kind/profile, physical width/height in mm, quantity, background, border settings, and layers. Defaults are 45 × 55 mm, four copies, sky blue, enabled gray 0.2 mm border. Joint initialization overrides dimensions/kind as needed. `Photo.validate()` checks dimensions, quantity, and border thickness.

`Placement` stores `photo_id`, copy index, zero-based page index, and physical `x/y/width/height` in mm. Placement coordinates have their origin at the page's top-left. The PDF exporter converts to ReportLab's bottom-left origin.

`Job` stores ID/name, photos, placements, page count, and print settings. Jobs serialize to JSON via dataclasses and reconstruct layers through `from_dict()` methods.

**Default-setting caveat:** the generic `Job` dataclass and some legacy settings still default to 2 mm horizontal / 3 mm vertical gaps. `StudioWindow.start_workflow()` explicitly overrides these to **0.2 / 0.2 mm**. Read the active call path before changing defaults or claiming every settings field controls the focused interface.

### Rendering rules

- Raster dimensions: `round(mm / 25.4 * dpi)`, with a minimum of one pixel.
- PDF dimensions: `mm * 72 / 25.4`, without rounding to raster pixel sizes.
- Layer center is normalized against the canvas, and may extend outside its bounds.
- Scale multiplies a baseline cover factor: `max(canvas_width/image_width, canvas_height/image_height)`.
- Calculate that baseline before expanding the image for rotation. Otherwise rotation incorrectly changes apparent scale.
- `prepare_layer()` applies mask edges, saved strokes, tone changes, and flips. `render_photo()` composites visible layers at their transforms over the selected background.
- Mask stroke points use normalized image coordinates; radius is a fraction of image width. Canvas mapping accounts for flips before storing strokes.
- `render_photo()` itself does not draw the border. PDF export draws an inside vector border; edited-image export adds an inside raster border separately.
- Locked layers cannot be directly transformed/painted. Hidden layers are excluded from the final composition.

## 6. Persistent storage and backup

Production data lives under:

```text
%LOCALAPPDATA%/StudioPhotoMaker/
  studio.db                     Jobs, config, profiles, export history
  library/
    library.db                  Photo/source serials, names, paths, crop regions
    sources/                    Copied original imports, named using content hashes
    photos/                     Prepared PNGs and .thumb.jpg thumbnails
  cache/                        Background-removed RGBA PNGs used by jobs
  job_assets/                   Materialized crops, including older workflows
  models/                       Optional locally installed ONNX models
```

`data_root()` creates this directory and falls back to the user's home directory if `LOCALAPPDATA` is unavailable. Never store user work under `sys._MEIPASS`, `build`, or a temporary extraction directory.

The main database uses SQLite WAL and contains:

- `jobs(id, name, payload, updated)` — JSON job snapshots.
- `config(key, value)` — JSON settings values.
- `profiles(name, payload)` — JSON profile definitions.
- `exports(path, created)` — export history.

The library database uses SQLite WAL and contains:

- `photos(serial INTEGER PRIMARY KEY AUTOINCREMENT, id UNIQUE, name, source, asset, thumb, width, height, deleted)`.
- `sources(serial INTEGER PRIMARY KEY AUTOINCREMENT, digest UNIQUE, name, asset)`.
- `source_regions(asset PRIMARY KEY, payload)` — serialized crop quadrilaterals/rotation.

`CropTray(root=...)` is the durable production library. `CropTray()` without a root retains a memory-only mode for older tests/callers. The memory-only mode has a total-pixel limit; persistent mode uses saved assets and lazy image loading.

`PreparedPhoto.image` loads its asset when needed; `size` can use stored dimensions without decoding it. Missing images raise a useful error, while thumbnails can display a Missing placeholder so the gallery remains usable.

Back up the **whole application-data folder with the app closed**, including cache files referenced by saved jobs. Older jobs may reference external files too. Asset paths are currently stored as paths, so restoring to a different user/location may require path migration; there is no dedicated portable archive/import feature.

Preserve SQLite photo serials, source assets, and job references when adding migrations. Soft deletion is deliberate. Do not implement blanket cache/library cleanup without checking saved-job dependencies.

Some comments in `cropping.py` still describe the earlier memory tray or say only selected crops become durable. The production implementation with `root` saves crops immediately; use the implementation and this distinction when interpreting those comments.

## 7. Background removal, framing, and threading

`find_background_model()` checks folders in this order:

1. Configured model directory, if present.
2. Application-data `models` directory.
3. Packaged/source-root `models` directory, using `sys._MEIPASS` when frozen.

Within each folder it prefers `u2net_human_seg.onnx`, then `u2netp.onnx`. The release bundles the human portrait model, approximately 176 MB.

`remove_background()` performs inference directly with **ONNX Runtime CPUExecutionProvider**. It does not import `rembg` at runtime. It reuses a model session guarded by a lock and uses four intra-op threads / one inter-op thread. Inputs are resized to 320 × 320, normalized, and fed as NCHW tensors; the predicted alpha is resized to the working image and multiplied by original alpha. Segmentation working images are capped at 4000 pixels per edge; general loading defaults to a 6000-pixel cap. Prepared image assets are therefore not a promise of unlimited camera-resolution processing.

Cached segmentation filenames hash the resolved source path, source modification time, model path, and model modification time. `force=True` requests regeneration. Cache PNG writes use a temporary file and replacement.

`frame_photo(photo, mode)` handles automatic framing, whole-image fit, or cover fill. It uses processed foreground bounds and optional OpenCV Haar frontal-face boxes. One combined joint layer is treated as a group; multiple subject layers receive separate canvas positions. Alignment helpers can match detected head sizes and align bottoms.

Expensive work runs through `Worker(QRunnable)` and Qt signals. `StudioWindow.run()` manages busy state and disables the workspace while a job is active. Update widgets in the GUI-thread completion callback, not inside worker functions.

**SQLite thread distinction:** the main `Database` connection uses SQLite's normal thread checks and belongs to the GUI thread. Read settings before starting workers; do not call its methods from a worker. The library connection explicitly uses `check_same_thread=False` and an `RLock` around database operations. Do not remove that protection or pass either connection around as if it were unrestricted.

Active inference has no mid-call cancel mechanism. Closing the window waits for worker completion. Keep the UI responsive through worker dispatch rather than attempting to run inference in a button callback.

## 8. Development setup and build

Current workspace: `D:\Custom Software\Photo Print`. Shell examples below are PowerShell and assume that directory is current.

The existing project-local runtime is **Python 3.12.10 x64** at `.tools/python/python.exe`. A `.venv` also exists; do not assume the system `python` command is available or that every interpreter has the same packages.

Run source with the local runtime:

```powershell
& '.\.tools\python\python.exe' main.py
```

On a development machine with standard Python 3.12 x64 installed, `setup.bat` creates `.venv` and installs `requirements.txt`. For a version-pinned install into an already-created environment:

```powershell
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
```

`run.bat` prefers `.venv/Scripts/pythonw.exe`, then `.tools/python/pythonw.exe`. `build.bat` chooses the equivalent Python console executable and runs PyInstaller. Setup installs packages; it does not itself guarantee that a portrait model is present.

Primary dependencies are PySide6-Essentials, Pillow, opencv-python-headless, NumPy, ONNX Runtime, and ReportLab. pytest and pypdf support testing; PyInstaller supports packaging. `requirements-lock.txt` records the exact tested versions. Existing development installations may contain extra experimental packages; those are not required runtime dependencies.

Clean build:

```powershell
& '.\.tools\python\python.exe' -m PyInstaller --clean --noconfirm StudioPhotoMaker.spec
```

The spec makes an **onedir**, GUI application (`console=False`), collects ONNX Runtime libraries and OpenCV data, and excludes heavy unused packages such as rembg, numba, scipy, skimage, matplotlib, and Qt WebEngine.

**Model packaging caveat:** the spec includes `%LOCALAPPDATA%/StudioPhotoMaker/models/u2net_human_seg.onnx` only if that file exists. A build can succeed without it. Ensure the model exists at build time, verify `_internal/models` in the output, and run the frozen acceptance workflow without an external model override. Do not redirect `LOCALAPPDATA` to an empty test folder while building unless the expected model is available there.

The latest delivered package includes README, validation, checklist, and attribution documents copied alongside the executable. The spec does not currently automate those documentation copies. After a new release, copy updated distribution docs as needed. Changes to source code require rebuilding to appear in the EXE; documentation-only updates do not require rebuilding it.

## 9. Verification and reproducible diagnostics

### Automated tests

```powershell
& '.\.tools\python\python.exe' -m pytest -q
```

The recorded release result is **35 tests passed** on Windows. This is a historical validation result, not a guarantee for future changes. Two existing Pillow `getdata` deprecation warnings were recorded in synthetic-image tests.

Tests cover physical geometry, parsed PDF placement, quantities/pagination, boundary/overlap checks, original preservation, EXIF orientation, perspective cropping, actual Qt mouse transforms, editable mask behavior, undo/redo, library persistence, source deduplication, lazy images, serial selection, and joint input variants.

Relevant suites:

- `test_core.py`: core image/layout/PDF behavior.
- `test_ui.py`: earlier interface regression coverage.
- `test_guided_ui.py`: focused workflow behavior.
- `test_cropper.py`: crop preparation and interaction.
- `test_final_workflow.py`: durable serial library, framing, real transform gestures, mask/tone serialization, combined joints, picker search, and tiled demo counts.

Some demo-dependent cases skip if user fixtures are absent. Review skips before claiming the demo behavior was checked on a different machine.

### Current full acceptance

`--verify-studio DEMO_FOLDER OUTPUT_FOLDER` runs the actual workflow against the supplied demos and produces JSON results, screenshots, image renders, and PDFs. It creates library entries and saves jobs: **always give it a fresh isolated application-data directory**, not the user's production library.

Example packaged acceptance with temporary environment overrides restored afterward:

```powershell
$previousLocalAppData = $env:LOCALAPPDATA
$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousModelOverride = $env:STUDIO_VERIFY_MODEL_DIR
$reviewFolder = Join-Path (Get-Location) ('.tools\handoff-review-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
try {
    $env:LOCALAPPDATA = Join-Path $reviewFolder 'user-data'
    $env:QT_QPA_PLATFORM = 'windows'
    Remove-Item Env:\STUDIO_VERIFY_MODEL_DIR -ErrorAction SilentlyContinue
    $reviewOutput = Join-Path $reviewFolder 'results'
    $reviewArguments = '--verify-studio "Demo" "' + $reviewOutput + '"'
    $reviewProcess = Start-Process -FilePath '.\dist\StudioPhotoMaker\StudioPhotoMaker.exe' -ArgumentList $reviewArguments -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -Wait -PassThru
    $reviewProcess.ExitCode
    Get-Content (Join-Path $reviewOutput 'result.json')
}
finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    $env:QT_QPA_PLATFORM = $previousQtPlatform
    $env:STUDIO_VERIFY_MODEL_DIR = $previousModelOverride
}
```

For source acceptance, use `main.py --verify-studio Demo OUTPUT_FOLDER` with the same data isolation. Set `STUDIO_VERIFY_MODEL_DIR` to a real installed model folder if the isolated source run has no model of its own. Clearing this variable during frozen acceptance checks that the packaged model is sufficient.

Other CLI modes are `--smoke-test OUTPUT.png`, `--verify-cropper SOURCE OUTPUT_FOLDER`, and `--verify-runtime SOURCE OUTPUT_FOLDER`. The smoke test grabs the dashboard and exits; it is not equivalent to full processing validation. Older scripts/diagnostics can reflect earlier workflows; prefer the current tests and `--verify-studio` for release acceptance.

### Recorded demo results

| Input | Saved prepared photos |
|---|---:|
| `Demo/Pictures/IMG_0007.jpg` | 9 |
| `Demo/Pictures/IMG_0008.jpg` | 11 |
| `Demo/Pictures/IMG_0009.jpg` | 18 |
| `Demo/portrait (1).jpg` | 8 |
| `Demo/portrait (2).jpg` | 9 |
| `Demo/portrait (3).jpg` | 9 |
| Four `Demo/joint (...).jpg` combined examples | 4 total |
| **Total** | **68** |

The full source acceptance passed in 32.28 seconds. A clean standalone build passed in 34.2 seconds, exit code 0, using fresh app data and only its bundled model. These timings describe the development machine, not a performance guarantee.

The release acceptance checked source/crop persistence, serials, automatic framing, combined and separate joint composition, editable mask/tone settings, PDFs, restart behavior, lazy loading, and unchanged original-file hashes. Screenshots and rendered outputs were inspected. Face detectors can return false positives; detector box counts are not actual person-count guarantees.

Local evidence, if still present:

- `.tools/studio-release-check/result.json` and its screenshots/PDFs.
- `.tools/studio-release-data/` — isolated acceptance user data.
- `.tools/final-review/` — source-run acceptance artifacts.
- `.tools/studio-release-build.log` — build log.

Keep user demo photos and diagnostic portraits local. They are private test inputs, not assets to upload or bundle for end users.

The Git repository excludes these private fixtures, local tools, database files, model weights, and generated application folders. Tests that explicitly depend on the supplied demo images skip in a clean source checkout. See `GITHUB.md` for publishing and the distinction between source uploads and packaged release assets.

## 10. Known limitations and remaining work

- Physical printer acceptance is still outstanding: print at 100%, measure with a ruler, and check driver margins. PDF nominal size was tested programmatically.
- Automatic cropping, face placement, and background removal can require manual correction on difficult, low-resolution, or damaged inputs. Hair/edge quality depends on the source and model.
- Small images cannot gain authentic detail merely through scaling or 300 DPI metadata.
- No HEIC/RAW import, PSD compatibility, or full Photoshop feature set.
- No direct printer-driver scaling application; saved calibration preferences do not silently alter exact nominal photo-PDF geometry.
- No interruption of an active inference call.
- Library/assets are path-based; no complete portable project archive or cross-user restore migration UI.
- Generic/legacy settings and the focused interface do not necessarily expose the same options; trace active behavior before extending either.
- Layout overlap validation compares placement pairs and can become expensive for very large orders. Optimize with per-page grouping/spatial indexing if actual workloads justify it, while preserving validation.
- Government-photo presets are size starting points, not current-rule or application-acceptance guarantees. Do not claim background editing is allowed for every authority.

Optional future work is listed in `TODO.md`. No additional feature was left pending merely because the last user asked for this handoff document.

## 11. Guidance for the next AI or developer

1. Read this file and `README.md`, then inspect the active source path for the requested change. Treat code and freshly run checks as authoritative if this document becomes stale.
2. Preserve the Cropper-first workflow, durable serial library, combined-joint option, exact physical sizes, and original-file safety.
3. Do not test import/diagnostic workflows against the user's real app-data directory. Isolate `LOCALAPPDATA` and restore environment variables afterward.
4. Keep GUI work on the GUI thread and expensive image processing in workers. Respect the two database connections' different threading rules.
5. Keep canvas previews, final image rendering, and PDFs consistent when changing transforms, strokes, borders, or dimensions. Screen-only pose marks must remain absent from exports.
6. Preserve backward compatibility of serialized jobs/layers; add defaults or explicit migrations for new fields. Do not recycle serials or delete assets referenced by saved work.
7. Test the behavior affected by a change. For processing/persistence/release changes, run the relevant automated suite and full demo acceptance. Do not treat a dashboard screenshot as end-to-end proof.
8. Rebuild the EXE after code changes and validate the frozen app separately. A source run can accidentally rely on development packages, an installed model, or settings absent from an end user's PC.
9. Update `README.md`, `VALIDATION.md`, `TODO.md`, and this file when their claims change. Distinguish new verification from historical recorded results.
10. Report what changed, how it was verified, and material remaining limits plainly. Avoid claiming perfect segmentation, official document compliance, or physically measured printer output without evidence.

Useful starting points: UI changes → `studio_window.py` / `transform_canvas.py`; crop/library changes → `cropper.py` / `cropping.py`; background/edge/color changes → `imaging.py`; automatic fitting → `framing.py`; print geometry → `layout.py` / `pdf.py`; packaging → `StudioPhotoMaker.spec`.
