# Studio Photo Maker

Windows desktop software for local crop preparation, portrait and joint editing, and physically accurate A4 PDFs. Python is **not required** for the standalone application.

For a detailed architecture, workflow, storage, build, and testing handoff for developers or AI assistants, read [PROJECT_INFO.md](PROJECT_INFO.md).

Repository setup, fresh-clone instructions, and release distribution are described in [GITHUB.md](GITHUB.md). This source repository excludes private demo photos, local tools, model weights, and generated executables.

## Start

For the updated Windows application, open `dist\StudioPhotoMaker-v2\StudioPhotoMaker.exe`. Keep the **entire** folder together, including `_internal`. The previous working package remains in `dist\StudioPhotoMaker`. The bundled portrait model allows offline processing. Photographs are never uploaded. A source clone does not include generated application folders; use the development setup below.

For source development on this PC:

```powershell
& '.\.tools\python\python.exe' main.py
```

Or double-click `run.bat`. On a development PC with Python 3.12 x64, run `setup.bat` to create `.venv` and install dependencies, then `run.bat`. `requirements-lock.txt` records the tested versions. A fresh source clone has no `.tools` runtime; use `.venv\Scripts\python.exe` for the commands in this guide. Install the portrait model through Settings or `python -m scripts.install_model` using that environment before background removal or packaging.

## 1. Cropper and saved library

Import a scan sheet or camera JPG/JPEG/PNG/WEBP/BMP/TIFF. Drag-and-drop and Ctrl+O open Cropper. Sources are copied to local application data so they survive moving the original file. They receive source serials such as `S000001`; identical source bytes are deduplicated.

Automatic detection finds separate prints, including tightly tiled passport sheets and faint low-contrast prints. Drag regions, move corner **or edge** handles, rotate crops, or draw new regions on empty areas. Crop undo/redo also works with Ctrl+Z / Ctrl+Shift+Z while Cropper is open. Preview Crop checks the extracted result before saving. Perspective extraction straightens tilted prints. Phone EXIF orientation is respected, and local face detection attempts to orient extracted portraits upright. Wheel zooms; double-click a region to inspect it; Fit Sheet returns to the whole source. Use Whole Image is useful for a single camera portrait or an already-combined couple photo.

Keep Selected Crop or Keep All Crops saves prepared photos automatically and opens the Saved Library tab. Each has a permanent, never-reused serial such as **#000001**. Sources, regions, photo names and serials survive restarts. Search by serial/name, sort newest/oldest/serial, and filter Individual or Joint. Initial categories use image format/name; use Mark Individual / Mark Joint to correct them. The gallery queries up to 200 matching entries; full-resolution images load only when needed. Double-click a saved photo for a larger preview.

Removing a library entry hides it; files referenced by saved jobs are retained. Choose Removed Photos and Restore Selected to recover the same serial. Originals are never overwritten.

## 2. Portrait and joint makers

Portrait defaults to **45 x 55 mm**. Joint defaults to **55 x 45 mm**. Edit dimensions directly or swap width/height.

- Portrait: choose one prepared photo.
- Joint: choose **one existing combined photo**, or **two separate portraits**. Use checkboxes to select photos across serial searches.

Backgrounds are removed locally, then automatic framing places heads and shoulders on the canvas. Combined joint photographs remain one layer and are fitted as a group; separate subjects can be adjusted independently. Sky blue `#ADD8E6` is selected by default. Use Auto Frame, Fit Photo or Fill Canvas for a different starting composition. Positioning guides are screen-only and never printed.

Open **Photo Profiles** from the header to add, edit, duplicate, delete, search, or restore missing starter profiles, and choose separate individual/joint defaults. Starter regional categories include Malaysia, India, USA, UK, Bangladesh, and Custom. Each profile stores dimensions, category/orientation, quantity, background, border, and layout defaults. All presets are editable studio starting points; verify current authority requirements separately.

In Transform, search the profile selector and click **Apply Selected Profile**. It applies photo/print settings while keeping layers, masks, brush strokes, and transforms. Changed dimensions/layout reset sheet positions deliberately; applying a profile never overwrites the original image.

## 3. Editing controls

The preview supports proportional corner scaling, a rotation handle, live layer dragging and center snapping. Numeric position/zoom/rotation controls provide precision. Layers can be shown/hidden, locked, flipped, brought forward or sent back. Align Bottoms and Match Head Sizes assist joint composition. Hidden layers are omitted from exports.

Finish controls include brightness, contrast, saturation and sharpness, mask contraction/expansion, softness, and optional **Reduce Edge Halo**. Erase/Restore brushes refine the mask without modifying the source. Adjustments and brush strokes remain editable and are applied to exports. Restore reveals original pixels, so use it over the subject rather than the old background. Settings → Processing offers Fast, Balanced, and Fine Edges quality, plus the preferred initial framing. Fine Edges uses local guided matte refinement; difficult hair/edges can still need manual correction.

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

Jobs auto-save after editing pauses. Explicit Save Job and Saved Jobs remain available. Export Edited Photo writes PNG or high-quality JPEG at the chosen render DPI (300 by default), with inside borders and atomic file replacement. The Before/Original Background option is a comparison view and does not change exports.

## 4. Print

Set border enable/color/thickness and copy quantity. Quick quantities: **2, 4, 6, 8, 10, 12**, plus a numeric field and **Add/Remove 2 Copies**. Quantity changes update the open sheet preview and retain existing copy positions where possible. Appearance and subject-position edits also retain sheet placements. Larger orders create pages automatically.

Choose a layout in Print or directly beside the sheet preview:

- **Automatic**: centered rows, preserving the existing mixed-size packing behavior.
- **2 columns × 2 rows**: a centered four-photo block; extra copies continue on additional pages.
- **Custom rows and columns**: a centered grid using your row/column counts.
- **Maximum-fit**: fill a centered grid with the most full-size copies that fit the selected page.

Portrait copies stay portrait and joint copies stay landscape unless you explicitly change their dimensions. Paper orientation is independent. Set margins and horizontal/vertical gaps in millimetres; studio defaults are 10 mm margins and 0.2 mm gaps. Arrangements that do not fit explain the available capacity and alternatives. No layout silently shrinks or rotates photographs.

Photos can be moved manually. Overlap, configured margins (for new jobs), physical dimensions, and copy identity are checked before PDF export. Existing valid placements are retained when reopening preview. Reset Automatic Layout is an explicit way to discard manual placement changes. Dashed page margins are editing overlays and are not exported.

Print dimensions use exact `mm * 72 / 25.4` PDF points. A4 is exactly 210 x 297 mm (or 297 x 210). Borders are drawn **inside** the selected dimensions. Raster rounding does not alter the PDF footprint. Preview and PDF use the same composition and inside-border geometry; PDF borders remain sharp vector strokes.

With 10 mm page margins, 45 mm photos fit **four across portrait A4** or **six across landscape A4**. At 35 mm wide, five fit across portrait A4. Larger orders create additional pages without shrinking photos. Low-resolution inputs produce an export warning; software cannot restore detail absent from a small source image.

Print PDFs at **Actual Size / 100%**, never Fit to Page. Physical printer margins and ruler calibration must be checked on the studio printer. Calibration is stored for manual use in the printer driver; PDF dimensions remain nominal and exact.

## Settings

Settings is organized into General, Photo, Print, Profiles, Processing, and Storage tabs. Startup workflow, save folder, dimensions, default copies/background/border, page layout, DPI, guides, and image-processing preferences persist. They apply to new jobs; existing jobs keep their saved settings. Saved Photo/Print preferences override the selected default profile's corresponding settings for new jobs. Applying a profile explicitly in the editor uses that profile's complete photo/layout settings.

## Local data and backup

Everything is stored locally under `%LOCALAPPDATA%\StudioPhotoMaker`:

- `studio.db`: jobs, settings, size profiles and export history.
- `library\library.db`: permanent source/photo serials, metadata and crop regions.
- `library\sources`: saved original imports.
- `library\photos`: prepared photos and small thumbnails.
- `cache`: background-removed images referenced by saved jobs.
- `job_assets`: crops from earlier app versions.
- `models`: optional installed models; the packaged model is also usable directly.

Settings → Storage shows the data folder, measures usage, and creates a backup ZIP of jobs, settings, sources, prepared photos, and cache assets. It uses SQLite snapshots that include committed WAL transactions and includes external images referenced by older jobs. Downloaded models are optional in the backup; an installed model is retained when restoring a backup without models.

Restore verifies file hashes and database integrity in a staging folder, remaps image/database paths to this PC, then asks before replacing data and restarting. The entire previous data directory is retained alongside the restored one as `StudioPhotoMaker.before-restore-...`. A restore journal recovers an interrupted directory swap on the next startup. Keep backup ZIPs private and outside the application-data folder.

Clear Old Unreferenced Cache Files only removes old files in `cache`, preserving references from **all** saved jobs and the current edit. It never deletes library/source assets. You can also back up the entire application-data folder manually with the app closed. User data is not stored in a PyInstaller temporary directory.

## Test and build

```powershell
& '.\.tools\python\python.exe' -m pytest -q
& '.\.tools\python\python.exe' -m PyInstaller --clean --noconfirm --distpath dist\candidate --workpath build\candidate StudioPhotoMaker.spec
```

With a standard virtual environment substitute `.\.venv\Scripts\python.exe`. Or use `build.bat`, which builds to `dist\candidate\StudioPhotoMaker` to preserve working releases. Validate that candidate before promoting or distributing it. The build requires the portrait model at `%LOCALAPPDATA%\StudioPhotoMaker\models\u2net_human_seg.onnx` and fails clearly if it is missing. Model installation is available in Settings or the installer module. Distribute the whole validated application folder.

See `VALIDATION.md` for concrete results and `THIRD_PARTY.md` for component/model attribution.

## Practical limits

This is a focused studio editor, not a PSD-compatible Photoshop replacement. HEIC/RAW import is not included. Automatic crop/face detection and segmentation can require manual correction, especially on low-resolution or damaged scans; edge brushes are provided. Active inference cannot be interrupted mid-call. Government-document presets are print starting points and require checking the authority's current rules; digital modification may be prohibited. Physical printer/ruler acceptance remains a studio-side check.
