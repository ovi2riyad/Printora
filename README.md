# Printora 3.1 — Studio Photo Maker

Offline Windows desktop software for studio photo preparation, customers, orders and exact-size A4 PDFs. Built with Python and PySide6. The standalone application **does not require Python**, an account, a server, or a paid AI service.

Source: [ovi2riyad/Printora](https://github.com/ovi2riyad/Printora). Developer/AI handoff: [PROJECT_INFO.md](PROJECT_INFO.md). Executed phase reports: [PHASE_REPORTS_3_0.md](PHASE_REPORTS_3_0.md). Publishing: [GITHUB.md](GITHUB.md).

## Start

Run **`dist/installers/Printora-3.1.0-Setup.exe`** to install. Accept the normal Windows administrator prompt. The default location is **`C:\Program Files\Printora`** on a standard Windows installation. Setup automatically creates a **Printora Desktop shortcut**, a **Start menu / All apps entry**, and an **Installed apps uninstall entry**. Launch Printora normally from either shortcut; Python is not required.

Setup upgrades the same installation. Uninstall removes installed application files and shortcuts while retaining your photo/customer data at `%LOCALAPPDATA%\StudioPhotoMaker`. Back up that data before upgrades. The installed binary is `Printora.exe`; the portable edition at `dist/Printora-3.1/StudioPhotoMaker.exe` still needs its whole folder, including `_internal`. Older v3/v2/original packages are retained separately.

A GitHub source checkout does not include generated EXEs, model weights, local tools, databases or private photographs. It is for developers. Standalone packages include the portrait model and work offline.

## Dashboard and normal workflow

Nine modules: **Cropper, Portrait Maker, Joint Photo Maker, Multi Photo Print, Customers, Orders, Photo Library, Print Recipes, Settings & Backup**. Quick-access lists show recent customers/orders/jobs and frequently applied recipes.

The **Studio tools** dashboard button adds batch preparation, contact sheets, order QR lookup, receipts, printer measurements and statistics. Batch finishing supports up to 200 library photos, local background removal, Fast/Balanced/Fine quality, framing, replacement color, tone factors and a recipe. Review each result, mark it reviewed, then save it. Errors are reported per photo. Open a saved result in its maker for correction or add reviewed jobs to a print session. Save successful results before starting another batch; unsaved review results are session-only.

Contact sheets paginate numbered thumbnails; photo names can be disabled, and customer names/mobiles are opt-in. QR images contain only a local order UUID and resolve against this library or its backup; paste/scan the code or import its image to find the order. Receipts offer an optional amount/currency and opt-in contact fields/notes. These are simple receipts, not tax/accounting software. Calibration PDFs contain 100 mm rulers/square and portrait/joint boxes; stored per-printer measurements provide driver correction references without changing photo PDF sizes. Statistics distinguish generated-order copies from copies in orders staff marked Completed, and group order months in UTC.

Optionally register/select a customer, import and crop their photos, review them in a maker, then add reviewed compositions to Multi Photo Print. Choose each person's copies, arrange/review the sheet, and create an order for searchable reprint history. Customer registration is optional.

## Cropper and library

Import JPG/JPEG, PNG, WEBP, BMP and TIF/TIFF using Ctrl+O, drag-and-drop or the import button. Sources are copied locally and deduplicated by file contents. Sources get permanent IDs such as `S000001`; prepared photos get independent permanent serials such as `#000001`. Serials, names, originals and crop regions survive restarts.

Automatic detection handles separate or tiled prints. Move regions, drag corner/edge handles, draw additional regions, rotate, undo/redo and preview extraction. Perspective extraction straightens tilted prints; EXIF orientation is respected. **Use Whole Image** handles a camera portrait or already-combined couple image. Difficult scans may need manual correction.

Cropper's optional customer row supports existing/new customer assignment. Crops inherit source assignments; reimporting identical bytes does not remove another customer's links. Existing photos can be assigned later, including in bulk.

The full Photo Library offers adjustable large/compact/list views, serial/name/customer-name/mobile search, type/date filters, 200-result pages, previews, classification, prefix-plus-serial bulk rename and customer assignment. Open a customer's Photographs to filter by that customer; unlinking removes the association without deleting images. Historical imports without reliable dates show as unknown.

Selections have blue borders, checkmarks, tint and a selected-serial summary. They persist across searches and view changes. **Select visible** selects the current page; **Clear selection** clears retained off-screen selections too. Full images load when needed. Photo removal is a soft removal; recover entries in Cropper → Saved Library → Removed Photos. Saved work retains its files.

## Portraits, joints and editing

Portrait defaults to **45 × 55 mm**; joint defaults to **55 × 45 mm**. Both are editable. Joint accepts one combined couple image or two separate portraits. Loading prepared inputs removes backgrounds locally; sky blue **`#ADD8E6`** is the replacement default.

Framing offers **Balanced, Document and Custom** modes, independent physical margins, alignment, head/lower-edge anchors, scale and named presets. Balanced fits foreground without forcing bottom contact. Document framing uses face detection as a positioning aid. Combined joint subjects stay grouped; separate layers can be positioned independently. Fit/Fill and manual transforms remain available. Saved jobs retain their transforms when reopened. All pose/safe-area guides are screen-only.

Use direct movement, proportional corner resizing, rotation, numeric transforms, snapping, flips, visibility/locking, layer order, zoom/pan and undo/redo. **More editing tools** opens brush hardness/opacity, mask-only preview, background presets/recent colors, layer rename/duplicate, simple grouping and selected mask/tone reset. Group members share transforms; locked members remain unchanged.

Finish controls include brightness, contrast, saturation, sharpness, mask contraction/expansion, softness, halo reduction and Erase/Restore. Restore reveals original pixels and may reveal the old background if painted outside the subject. Fast/Balanced/Fine Edges use local CPU ONNX. Comparison/mask views do not change exports.

Jobs auto-save after idle editing. Ctrl+S saves the active composition or multi-photo session. Edited-image export writes PNG/JPEG at the selected DPI with an inside border and replacement background. PNG is not currently a transparent-cutout export workflow.

| Shortcut | Action |
|---|---|
| Ctrl+O / Ctrl+S | Import / save |
| Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y | Editor/crop undo / redo |
| V / E / R | Transform / erase / restore |
| [ / ] | Brush size |
| Arrows / Shift+arrows | Fine / larger nudge |
| Ctrl+wheel / Space+drag | View zoom / pan |
| Ctrl+0 / Ctrl+1 | Fit / 100% view |

## Multi Photo Print

Add multiple saved portrait/joint compositions, or select library photos for preparation and individual review. Each library input opens in its maker; click **Add reviewed photo to session** to continue. Finished compositions retain their dimensions, edits, backgrounds and borders. Session items have separate identities; editing one does not overwrite its origin job.

Set copies per person, use presets or Apply copies to all, duplicate/remove/reorder, and preview every page. Automatic paper orientation compares portrait/landscape A4 using the current engine, prefers fewer pages and retains orientation on ties. Manual override is available. Actual photographs are never silently shrunk, distorted or rotated to make them fit.

Automatic mode mixes sizes in centered rows. The 2×2/custom/maximum-fit grids give each composition its own page group. Orientation comparison is not an arbitrary nesting optimizer. The summary shows compositions/copies/pages/orientation and unused area; fragmented space may not fit another photo.

Sessions save compositions, quantities, settings and placements. Valid manual placements survive reopening and quantity changes. Arrange/reset explicitly replaces layout. **Create order** retains searchable business/reprint history; direct PDF export alone does not create an order.

## Customers, orders and reprint

Customers have independent `C000001` IDs, name, optional primary/alternative mobile, address/email/notes and registration/activity dates. Unicode digits/separators are normalized for mobile search while entered formatting is retained. Shared numbers are allowed with a duplicate warning. Archive/recovery preserves related work.

Orders have independent `O000001` IDs, customer/contact snapshots, composition/settings snapshots, quantities, notes, status and PDF events. Search historical mobile/name/order ID and filter date/status. Customer profiles link to photographs, saved compositions and order history. Double-click an order item to preview it.

Reprint workflow: **search mobile → customer → Orders / reprint → previous order → Reprint / duplicate → review copies/settings → Generate PDF**. This creates a new linked draft. Customer/profile/job edits do not rewrite old order settings or contact snapshots. Successful historical order PDFs are protected from normal export overwrites.

Statuses: Draft, Processing, Ready, Completed, Cancelled. Generating a PDF makes an order Ready; Completed is an operator action. PDF creation is not proof of physical printing. Attempts retain history; verified recovery markers reconcile interrupted PDF/history commits at startup.

## Print Recipes and exact output

Recipes extend the existing country profiles, with CRUD/search/rename/duplicate/defaults, missing-starter restoration and JSON import/export. They store photo dimensions, copies, background/border, preferred paper orientation, page margins/gaps, layout and rows/columns. Explicit application preserves layers/masks/transforms and resets incompatible placements. Recipe edits do not automatically modify saved jobs/orders. Existing global Photo/Print preferences still apply to new jobs; explicit recipe application uses the recipe's full values.

PDF geometry is exactly `mm × 72 / 25.4`; borders are inside the footprint. Defaults are 10 mm page margins and 0.2 mm gaps. At those margins, 45 mm-wide copies fit four across portrait A4 or six across landscape A4; 35 mm-wide copies fit five across portrait A4. Quantities paginate without resizing. Bounds/margins, overlap, copy identity, missing/duplicate copies and stale dimensions are validated.

Print at **Actual Size / 100%** and measure on the intended printer. Regional presets are editable starting points, not document-authority acceptance guarantees.

## Local data and backup

Production data: `%LOCALAPPDATA%\StudioPhotoMaker`.

- `studio.db`: jobs, config, profiles/recipes, customers/links, orders/items/events and sessions.
- `library/library.db`: source/photo serials, crop regions and photo metadata.
- `library/sources`, `library/photos`, `cache`, `job_assets`: originals, prepared photos, thumbnails and processed assets.
- `models`: installed optional models; standalone releases also bundle a model.
- `export-recovery`: temporary order export markers.

Additive migrations retain serials, paths and saved jobs. Pre-upgrade database snapshots are kept in `*-upgrade-snapshots`. Older EXEs may not understand newly saved 3.0 fields: roll back with a full pre-upgrade data backup, not an older EXE against newly edited data.

Settings → Storage creates verified manifest/checksum ZIP backups using SQLite snapshots including committed WAL data. They include customer/order/session records, local/referenced external images and available order PDFs; models are optional. Restore verifies inventory/hashes/database references, stages and remaps paths, retains the old data folder and restarts. Old backups migrate when opened. Backups contain private data and are not encrypted.

Cache cleanup protects references from saved jobs, historical orders and active edits, deleting only old unreferenced cache files. It never clears the library or recycles serials. Corrupt snapshots abort cleanup. Make manual whole-folder backups with the app closed.

## Develop, test and build

On a new development PC install Python 3.12 x64, run `setup.bat`, then `run.bat`. Use `requirements-lock.txt` for pinned packages. Install the portrait model in Settings or with `python -m scripts.install_model`; source clones exclude it.

On the original workstation:

```powershell
& '.\.tools\python\python.exe' main.py
& '.\.tools\python\python.exe' -m pytest -q
& '.\.tools\python\python.exe' -m PyInstaller --clean --noconfirm --distpath dist\candidate --workpath build\candidate StudioPhotoMaker.spec
```

Substitute `.\.venv\Scripts\python.exe` on standard setups. **`build.bat` creates both the candidate portable folder and Setup EXE**. Packaging requires `%LOCALAPPDATA%\StudioPhotoMaker\models\u2net_human_seg.onnx`. The first installer build downloads a checksum-pinned official Inno Setup compiler into ignored `.tools/inno`; this is a developer build tool. End users need no compiler or download. To use an installed compiler set `PRINTORA_ISCC` to its `ISCC.exe`. Use `build.bat --portable-only` to skip Setup, or `python -m scripts.build_release --skip-app --payload dist/Printora-3.1` to regenerate Setup after updating release documents. Validate source, frozen candidate and installation before promotion. See [VALIDATION.md](VALIDATION.md) and [THIRD_PARTY.md](THIRD_PARTY.md).

## Limits and optional follow-up

No HEIC/RAW, PSD compatibility or cancellation inside an ONNX inference call. Difficult hair/scans and low-resolution inputs need review; software cannot recreate authentic missing detail. Browsing is bounded, but lightweight legacy library metadata remains for compatibility. Very large orders still need memory/time proportional to PDF content despite bounded preview/raw-image caches. Physical printer acceptance remains outstanding.

Phase 6 tools and the Windows installer are included in 3.1. No Python runtime dependency or mandatory online processing service was added. Complex-script PDF shaping can depend on the available font; review printed customer labels. Physical printer acceptance still requires printing and measuring on your equipment.
