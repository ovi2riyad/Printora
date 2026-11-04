# Studio Photo Maker

Windows desktop software for local crop preparation, portrait and joint editing, and physically accurate A4 PDFs. Python is **not required** for the standalone application.

For a detailed architecture, workflow, storage, build, and testing handoff for developers or AI assistants, read [PROJECT_INFO.md](PROJECT_INFO.md).

Repository setup, fresh-clone instructions, and release distribution are described in [GITHUB.md](GITHUB.md). This source repository excludes private demo photos, local tools, model weights, and generated executables.

## Start

For the packaged Windows application, open `dist\StudioPhotoMaker\StudioPhotoMaker.exe`. Keep the **entire** folder together, including `_internal`. The packaged portrait background model allows offline processing. Photographs are never uploaded. A source clone does not include this generated application folder; use the development setup below.

For source development on this PC:

```powershell
& '.\.tools\python\python.exe' main.py
```

Or double-click `run.bat`. On a development PC with Python 3.12 x64, run `setup.bat` to create `.venv` and install dependencies, then `run.bat`. `requirements-lock.txt` records the tested versions. A fresh source clone has no `.tools` runtime; use `.venv\Scripts\python.exe` for the commands in this guide. Install the portrait model through Settings or `python -m scripts.install_model` using that environment before background removal or packaging.

## 1. Cropper and saved library

Import a scan sheet or camera JPG/JPEG/PNG/WEBP/BMP/TIFF. Drag-and-drop and Ctrl+O open Cropper. Sources are copied to local application data so they survive moving the original file. They receive source serials such as `S000001`; identical source bytes are deduplicated.

Automatic detection finds separate prints, including tightly tiled passport sheets. Drag regions, move their corner handles, rotate crops, or draw new regions on empty areas. Perspective extraction straightens tilted prints. Phone EXIF orientation is respected, and local face detection attempts to orient extracted portraits upright. Wheel zooms; double-click a region to inspect it; Fit Sheet returns to the whole source. Use Whole Image is useful for a single camera portrait or an already-combined couple photo.

Keep Selected Crop or Keep All Crops saves prepared photos automatically. Each has a permanent, never-reused photo serial such as **#000001**. Source images, crop regions, photo names and serials survive app restarts. Search by serial/name or rename a photo. The gallery displays up to 200 recent matches; search finds older entries. Full-resolution saved images load only when needed.

Removing a library entry hides it; files referenced by saved jobs are retained. Originals are never overwritten.

## 2. Portrait and joint makers

Portrait defaults to **45 x 55 mm**. Joint defaults to **55 x 45 mm**. Edit dimensions directly or swap width/height.

- Portrait: choose one prepared photo.
- Joint: choose **one existing combined photo**, or **two separate portraits**. Use checkboxes to select photos across serial searches.

Backgrounds are removed locally, then automatic framing fills the canvas naturally and brings clothing to its lower edge. Joint framing keeps a combined photograph together; separate subjects can be adjusted independently. Sky blue `#ADD8E6` is selected by default. Use Auto Frame, Fit Photo or Fill Canvas for a different starting composition. Positioning guides are screen-only and never printed.

## 3. Editing controls

The preview supports proportional corner scaling, a rotation handle, live layer dragging and center snapping. Numeric position/zoom/rotation controls provide precision. Layers can be shown/hidden, locked, flipped, brought forward or sent back. Align Bottoms and Match Head Sizes assist joint composition. Hidden layers are omitted from exports.

Finish controls include brightness, contrast, color saturation and sharpness, plus mask contraction/expansion and softness. **Erase** and **Restore** brushes refine the background mask without modifying the source. Brush strokes and adjustments are saved as editable settings and are applied to final-resolution exports. Restore reveals original image pixels, so use it over the subject rather than the old background.

| Shortcut | Action |
|---|---|
| V / Ctrl+T | Move/transform tool |
| E / R | Erase / Restore mask |
| [ / ] | Smaller / larger brush |
| Escape | Return to move tool |
| Drag corner | Proportional scaling |
| Drag rotation handle | Rotate selected layer |
| Wheel | Scale selected layer |
| Ctrl+wheel | Zoom the view |
| Space+drag | Pan the view |
| Arrows / Shift+arrows | Fine / larger nudge |
| Ctrl+0 / Ctrl+1 | Fit view / 100% view |
| Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y | Undo / redo |
| Ctrl+S | Save job |
| Ctrl+O | Import into Cropper |

Jobs auto-save after editing pauses. Explicit Save Job and Saved Jobs remain available. Export Edited Photo writes PNG or high-quality JPEG with 300 DPI metadata. The Before/Original Background option is a comparison view and does not change exports.

## 4. Print

Set independent copy quantity, border enable/color/thickness, and A4 orientation. Quick quantities: 4, 6, 8, 10, 12. Preview the sheet before exporting PDF. Photos can be moved manually; overlap and page boundaries are checked.

Print dimensions use exact `mm * 72 / 25.4` PDF points. A4 is exactly 210 x 297 mm (or 297 x 210). Borders are drawn **inside** the selected dimensions. Raster rounding does not alter the PDF footprint. A **0.2 mm white separator** runs between photos.

With 10 mm page margins, 45 mm photos fit **four across portrait A4** or **six across landscape A4**. At 35 mm wide, five fit across portrait A4. Larger orders create additional pages without shrinking photos. Low-resolution inputs produce an export warning; software cannot restore detail absent from a small source image.

Print PDFs at **Actual Size / 100%**, never Fit to Page. Physical printer margins and ruler calibration must be checked on the studio printer. The settings screen retains calibration and model preferences.

## Local data and backup

Everything is stored locally under `%LOCALAPPDATA%\StudioPhotoMaker`:

- `studio.db`: jobs, settings, size profiles and export history.
- `library\library.db`: permanent source/photo serials, metadata and crop regions.
- `library\sources`: saved original imports.
- `library\photos`: prepared photos and small thumbnails.
- `cache`: background-removed images referenced by saved jobs.
- `job_assets`: crops from earlier app versions.
- `models`: optional installed models; the packaged model is also usable directly.

Back up this **whole folder** and externally referenced images from older jobs. User data is not written into a PyInstaller temporary directory. SQLite transactions and atomic image/PDF file replacement protect completed writes.

## Test and build

```powershell
& '.\.tools\python\python.exe' -m pytest -q
& '.\.tools\python\python.exe' -m PyInstaller --clean --noconfirm StudioPhotoMaker.spec
```

With a standard virtual environment substitute `.\.venv\Scripts\python.exe`. Or use `build.bat`. Distribute the whole `dist\StudioPhotoMaker` directory. Building includes the portrait model from `%LOCALAPPDATA%\StudioPhotoMaker\models\u2net_human_seg.onnx`; keep that model available when rebuilding. Optional model installation remains available in Settings.

See `VALIDATION.md` for concrete results and `THIRD_PARTY.md` for component/model attribution.

## Practical limits

This is a focused studio editor, not a PSD-compatible Photoshop replacement. HEIC/RAW import is not included. Automatic crop/face detection and segmentation can require manual correction, especially on low-resolution or damaged scans; edge brushes are provided. Active inference cannot be interrupted mid-call. Government-document presets are print starting points and require checking the authority's current rules; digital modification may be prohibited. Physical printer/ruler acceptance remains a studio-side check.
