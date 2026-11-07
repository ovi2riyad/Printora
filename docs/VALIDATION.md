# Validation and release limits

This file records executed checks and separates software verification from physical studio acceptance. Current version: **3.3.2**. Live hosted results are available in [Windows tests](https://github.com/ovi2riyad/Printora/actions/workflows/tests.yml).

## Coverage

The suite covers image preservation/EXIF, crop geometry, source/library persistence and migrations, editable masks/transforms/undo, precise parsed PDF geometry, quantities and pagination, layout bounds/overlap, customers/orders/reprints, backup/restore/reference-aware cleanup, export protection, optional preferences, Save/Discard/Cancel, manual orientation, scanner/helper request protocols, Copy/Print Set, NID crop handles and workspace controls.

Publication adds checks for visible About credits and inclusion of guides/attribution in the generated payload. Installer acceptance uses a synthetic workflow so the cleaned checkout does not depend on private demo photos. Missing private-demo and historical-release fixtures are reported as skips, not as verified cases.

## Previous verification

Before removal of private fixtures, 3.3.1 passed **544 tests**, no failures/errors/skips, with two existing Pillow warnings. Its supplied NID front and back scans were checked at three detector sizes; source and frozen actual-NID workflows passed **33 checks** at 100% and 200% Windows scaling. The 36-check portrait/joint workflow saved 69 photos in source and frozen runs. Those are historical results; the private files are deliberately absent now.

The pale NID fix combines contrast thresholds and small edge-gap closing on detection previews. Cropped outputs and the centered actual PDF were visually inspected. Original bytes stayed unchanged. Existing manual crops remain untouched until explicit re-detection or re-import.

## Current release checks

| Executed local check | Result |
|---|---|
| Complete cleaned-source suite before viewport follow-up | **533 passed, 13 skipped**, no failures/errors; two existing Pillow warnings; 288.98 s |
| Focused native Windows tests | **42 passed, 7 skipped**, no failures; credits, payload, panel/folder and NID detector checks |
| Staged-source clean checkout, focused checks | **23 passed, 7 skipped**, no failures; imports verified from the exported source tree |
| Frozen simplified workflow, 100% / 200% | **32 checks passed** at each scale, including About credits |
| Frozen document / stabilization workflows | **25 / 31 checks passed** |
| Frozen synthetic two-photo sheet | **8 checks passed**, including real bundled CPU inference, crop extraction, portrait/joint composition, source preservation and PDF output |
| Changed-payload isolated installer | **6 checks passed**: files/model, shortcuts/registration, upgrade retention, installed startup, installed 32-check workflow, uninstall retention |
| Native viewport follow-up | **74 passed**, no failures/skips; includes the 512 × 384 logical-desktop regression in Light/Dark and existing native display-scale checks |

The 13 full-suite skips require deleted private demonstration images or a historical local acceptance database. No source regression was deleted to hide those skips. All device calls in synthetic workflow checks are intercepted before launching a driver helper. The model check uses generated artwork; it proves runtime operation, not photographic segmentation quality. A face-specific legacy diagnostic cannot frame that artwork and is not counted as a successful check.

The first hosted run caught an additional small-desktop failure at 200% scaling: the old 640-pixel width floor exceeded a 512-pixel logical viewport. Window minimums now respect the available desktop rather than enforcing that floor. A regression reproduced the old failure before the correction; the fix passed the 74-test native follow-up and was resubmitted to the full Windows workflow. The release links its final hosted run.

Frozen checks use a different working directory, Python-free PATH, fresh isolated app data and only the bundled model. The installer verifier uses a distinct test identity/location and leaves production data untouched. Final documentation copying changes no tested application code. Hosted CI is authoritative for its own clean Windows checkout; it does not replace bundled-model or installer acceptance. Release assets include an installer checksum.

## Remaining field checks

- Physical scanner Preview/ROI acquisitions, feeder behavior and color/B&W copying on actual devices.
- Physical printed dimensions at Actual Size / 100%, ruler checks, borders, separators, margins and color/edge quality.
- A real elevated production installation and a separate clean Windows machine without developer tools.
- Low-memory/integrated-graphics hardware and sustained real-workload testing.
- Publisher signing: Setup remains unsigned.

Native Qt checks use actual widgets/events with automated selections. A simulated printer submission is not a physical print. Windows queue availability is not proof of printer readiness. Automatic cropping, framing and segmentation still need review on difficult inputs.

No security penetration test, live dependency-advisory audit or exhaustive hostile-filesystem concurrency test is claimed. Retain backups before real upgrades, and keep private evidence/customer files outside public issues and release assets.
