# Validation results

## Automated suite

**35 tests passed** on Windows with Python 3.12.10 x64. Coverage includes:

- Exact millimetre-to-point conversion, A4 portrait/landscape page boxes and parsed PDF image placement matrices.
- Quantities, copy identity, centered rows, mixed dimensions, multi-page output, boundary/overlap validation, inside borders and calibration geometry.
- Imported originals preserved, corruption/missing files, EXIF camera orientation, perspective extraction and manual crop rotation.
- Real Qt mouse corner dragging and crop drawing, layer moving, proportional resize handles, rotation handles, mask brush commit, undo and redo.
- Automatic bottom-anchored framing, alpha erase/restore behavior, brightness changes without source mutation and serialized editable strokes.
- Permanent library serials across restarts, source-byte deduplication, source-copy survival after original removal, serials not reused after removal, names/regions saved, lazy full-image loading and missing-asset gallery placeholders.
- Existing combined joint input, two-source joint workflow, serial checkbox selection retained across searches and the three supplied tightly tiled passport-sheet counts.

Two existing Pillow getdata deprecation warnings occur in a synthetic-image test; they do not affect processing or test outcomes.

## GitHub source preparation

The reviewed Git source snapshot was exported into a separate directory and tested without private demo images, local model weights, or the generated application. It passed **32 tests**, with **3 expected skips** for the supplied private tiled-sheet fixtures, in **12.97 seconds**. Import resolution was checked to ensure the tests used the exported application source. This is a local clean-source check; hosted GitHub Actions results must be checked separately after pushing.

The staged source was also checked for excluded private/generated file paths, unexpectedly large files, and common credential signatures. Demo photos, local tools, databases, models, and packaged executables were excluded. `.github/workflows/tests.yml` runs the suite on Windows with isolated application data and offscreen Qt.

## Supplied-demo acceptance through the actual Windows UI

The complete source-run acceptance passed in **32.28 seconds**, producing **68 numbered saved photos**:

| Source | Prepared photos |
|---|---:|
| IMG_0007.jpg | 9 |
| IMG_0008.jpg | 11 |
| IMG_0009.jpg | 18 |
| portrait (1).jpg | 8 |
| portrait (2).jpg | 9 |
| portrait (3).jpg | 9 |
| Four already-combined joint examples | 4 |

The workflow validated automatically saved original imports and prepared crops, background removal on isolated inputs, new canvas framing, all four combined examples, a composition made from two separate sources, portrait/joint PDFs, editable mask/tone settings, library and job reopening, and unchanged hashes for every demo original. Library, portrait and joint screenshots and rendered output were inspected. Both subjects remained visible in the combined examples; the face detector can also return false positive boxes, so numeric detector counts are not a guarantee of face recognition or document compliance.

## Windows package

The final clean PyInstaller build succeeded. The standalone EXE then passed the entire supplied-demo acceptance with a fresh application-data directory and **only the bundled portrait model**, exiting **0** in **34.2 seconds**. It saved all **68** numbered photos, performed portrait/combined/separate-joint processing, verified editable settings and serials after restart, exported PDFs, and verified every original input hash stayed unchanged. The release uses dynamically linked Qt and CPU ONNX libraries and requires no system Python installation.

## Practical limits

A physical printer was not available: measure output at Actual Size / 100% on the intended printer. Model quality and source resolution remain photograph-dependent; mask brushes and manual framing are available. HEIC/RAW, Photoshop PSD compatibility, direct printer-driver scaling and interruption of an active inference call are outside this release. Everything, including diagnostic photos and outputs, stays on the local PC.
