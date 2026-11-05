# Validation results

## Automated suite

**57 tests passed in 13.86 seconds** on Windows with Python 3.12.10 x64 after the professional update. The baseline before changes was **35 passed in 10.26 seconds**. Coverage includes:

- Exact millimetre-to-point conversion, A4 portrait/landscape page boxes and parsed PDF image placement matrices.
- Quantities, copy identity, centered rows, mixed dimensions, multi-page output, boundary/overlap validation, inside borders and calibration geometry.
- Imported originals preserved, corruption/missing files, EXIF camera orientation, perspective extraction and manual crop rotation.
- Real Qt mouse corner dragging and crop drawing, layer moving, proportional resize handles, rotation handles, mask brush commit, undo and redo.
- Automatic bottom-anchored framing, alpha erase/restore behavior, brightness changes without source mutation and serialized editable strokes.
- Permanent library serials across restarts, source-byte deduplication, source-copy survival after original removal, serials not reused after removal, names/regions saved, lazy full-image loading and missing-asset gallery placeholders.
- Existing combined joint input, two-source joint workflow, serial checkbox selection retained across searches and the three supplied tightly tiled passport-sheet counts.
- Centered portrait/joint 2 × 2 presets on both A4 orientations, exact dimensions, pagination, custom grids, maximum-fit, configurable margins/gaps, useful fit errors, and 10,000-copy identity/overlap checks.
- Quantity presets and ±2 controls, live sheet updates, retained manual copy positions, profile application without loss of layers, default-profile geometry, persistent categorized preferences, and rejection of partial invalid preference writes.
- Additive profile/library migrations against synthetic legacy data and a copy of the previous release's databases, with original job payloads, paths, serials, and source database hashes preserved.
- Library category filtering, removed-photo recovery, missing-source serial retention, low-contrast detection, crop edge handles and undo/redo, alpha-preserving halo cleanup, fine matte refinement, and raster-allocation limits.
- Matching rendered image data in PDFs, custom vector border color/thickness, image-export pixels, guide exclusion, checksum-verified cross-path backup/restore, invalid/corrupt archive rejection, saved/current cache-reference protection, and recovery from an interrupted restore directory swap.

Two existing Pillow getdata deprecation warnings occur in a synthetic-image test; they do not affect processing or test outcomes.

## GitHub source preparation

For the original GitHub upload, a separate clean source snapshot passed 32 tests with 3 private-demo skips in 12.97 seconds; its hosted Windows run also passed (32 tests / 3 skips). These are historical baseline checks. The updated suite has 57 local cases; on GitHub, 3 private demo cases and 1 prior-release-data-copy case skip when the excluded local fixtures are absent. Hosted results for the current commit must be checked separately after pushing.

The staged source was also checked for excluded private/generated file paths, unexpectedly large files, and common credential signatures. Demo photos, local tools, databases, models, and packaged executables were excluded. `.github/workflows/tests.yml` runs the suite on Windows with isolated application data and offscreen Qt.

## Supplied-demo acceptance through the actual Windows UI

The expanded source acceptance passed in **40.16 seconds**, producing **68 numbered saved photos**:

| Source | Prepared photos |
|---|---:|
| IMG_0007.jpg | 9 |
| IMG_0008.jpg | 11 |
| IMG_0009.jpg | 18 |
| portrait (1).jpg | 8 |
| portrait (2).jpg | 9 |
| portrait (3).jpg | 9 |
| Four already-combined joint examples | 4 |

The workflow validated saved originals/crops, background removal, framing, all four combined examples, a two-source composition, portrait/joint PDFs, mask/tone/halo settings, restart behavior, and unchanged hashes for every original. It also exercised 2 × 2/custom/maximum-fit layouts, live quantities preserving coordinates, profiles preserving layers, crop undo/redo, serial recovery, Fine Edges inference, settings, and verified backup restoration to a different path. Library, editor, layout, settings screenshots and rendered outputs were inspected. Both subjects remained visible in combined examples; detector false positives mean box counts do not guarantee person recognition or document compliance.

## Windows package

The final clean PyInstaller candidate build succeeded. The updated standalone EXE passed the expanded supplied-demo acceptance with fresh application data and **only the bundled portrait model**, exiting **0** in **35.36 seconds**. It saved all **68** numbered photos and passed all 19 workflow checks, including new layouts, live quantities, profiles, crop history, fine-edge inference, storage/restore, preferences, restart persistence, PDFs, and unchanged original hashes. The updated package is promoted to `dist/StudioPhotoMaker-v2`; the previous `dist/StudioPhotoMaker` is retained separately and its executable hash is checked for preservation. The release uses dynamically linked Qt and CPU ONNX libraries and requires no system Python installation.

Evidence stays local in `.tools/upgrade-final-build.log`, `.tools/upgrade-final-frozen-check/result.json`, related screenshots/PDFs, and `.tools/previous-release-preserved.json`. The old release's 34.2-second acceptance is historical baseline evidence, not the current result.

## Practical limits

A physical printer was not available: measure output at Actual Size / 100% on the intended printer. Model quality and source resolution remain photograph-dependent; mask brushes and manual framing are available. HEIC/RAW, Photoshop PSD compatibility, direct printer-driver scaling and interruption of an active inference call are outside this release. Everything, including diagnostic photos and outputs, stays on the local PC.
