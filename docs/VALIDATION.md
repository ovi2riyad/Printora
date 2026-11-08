# Validation and release limits

This file records executed checks and separates software verification from physical studio acceptance. Current version: **3.4.1**. Live hosted results are available in [Windows tests](https://github.com/ovi2riyad/Printora/actions/workflows/tests.yml).

## 3.4.1 Crop, retouching and fit corrections

Before correction, native regressions reproduced the customer caption extending outside Cropper and covering Crop at three workspace widths. The corrected header uses bounded, elided captions. Actual photo fit uses the available height beside floating controls: on the 1366 × 768 test desktop the portrait was 445 logical pixels tall, approximately 21% larger than the supplied 3.4.0 screenshot, with zero outer scrolling. Cropper/Portrait/Joint/ID native checks passed at 100% and 200% scaling. A tall portrait retains its aspect ratio; empty horizontal space is not filled by stretching it.

New deterministic tests measure luminance/chroma variance reduction, retained step edges, tile seams, protected facial features/alpha, each tone/color/sharpening control, black preservation, Auto Fix repeatability/undo/locking, legacy fields, source/cache invalidation and original-file integrity. A private read-only comparison of prepared record #000063 also caught and corrected pale-skin white-balance contamination. Its SHA-256 stayed unchanged; the comparison stays local and is excluded from Git/releases. Subject-region noise estimation has a separate regression against blank-background bias.

The expanded local full suite passed **576 tests / 13 optional-fixture skips / zero failures/errors**, with two existing Pillow warnings, in **277.38 seconds**. This run preceded the final numeric-field-width correction and extra frozen acceptance assertions. The final dedicated/native tests and full hosted Windows results are linked in the release record. No pre-existing test was deleted or weakened. The first interim full run was stopped to correct the real-photo Auto Fix issue and is not counted as a completed pass.

Cold 1200 × 1600 processing measured about 5.6 seconds on this CPU; repeating unchanged pixel settings through the bounded cache measured about 4 ms. This is one local measurement, not a hardware performance guarantee. Preview now processes native working pixels before display downsampling, matching the export pipeline. Existing nonzero retouching settings can render differently under the improved algorithms; zero/default processing remains neutral. Automatic restoration of lost detail or Lightroom/Photoshop equivalence is not claimed.

The expanded synthetic workflow adds actual Auto Fix/repeat/undo, tight preview fit and Crop-header geometry checks to the prior 40-check acceptance. Frozen and installer results are reported for the new payload separately in the release. Physical scanning/printing remains deferred.

The first installed offscreen workflow exposed an overly strict new QA assertion: a width-limited portrait cannot also fill the viewport height without changing proportions. Acceptance now derives the attainable fit from both dimensions, with a separate narrow-view regression. The failed candidate result remains in local evidence; it is not counted as installer acceptance.

## 3.3.3 credits, licensing and naming

The public website is **https://enthugo.com**. GitHub and Settings → About now show a coordinated creator card for Riyad Ahmed Ovi, the requested email and the ChatGPT Codex development credit. About displays the complete MIT license locally in a readable dialog. The installer retains MIT, LGPL/GPL, PDFium/model and wheel-supplied component notices.

The public workspace name is **ID Card Print** in navigation, dashboard, workspace/settings titles, preview/save dialogs and newly generated job titles. Internal `nid` keys/classes and existing saved records remain compatible; this is a naming change, not a detection or layout change.

During this update the complete local suite passed **535 tests, 13 optional-fixture skips, no failures/errors**, with two existing Pillow warnings (296.83 s). This run preceded the final label-only rename. The final rename is checked through native widgets and the complete hosted Windows workflow. About/payload/offline-license regressions passed **4/4 on native Windows at both 100% and 200% scaling**. The earlier pre-viewer pass was 534 passed / 13 skipped.

After the label rename, the native About/document workflow suite passed **34 tests / 1 private-fixture skip** (46.35 s). Four direct native probes checked the dashboard/navigation, workspace/settings/job titles, preview title, and an actual offline MIT-license modal. Light/Dark creator cards and the license dialog were visually inspected.

The final bundled payload passed **32 workflow checks at 100% and 200% Windows scaling** (9.75 / 8.75 s), using a different cwd, Python-free PATH, fresh app data and no external model override. Its license inventory contains 57 notice/metadata files. The installer verifier now additionally checks the corrected publisher website and installed license/creator files, for seven acceptance checks in total. The release notes identify the published commit's full Windows CI and final installer acceptance; physical hardware tests remain deferred.

## 3.4 preview refinement

Native checks covered all four main workspaces at 100% and 200% Windows scaling with zero outer vertical scrolling. At 1366 × 768 / 100%, the portrait canvas viewport was approximately 1133 × 456 logical pixels; this is a measured layout result for the test desktop, not a promise for every display. At high scaling, compact icons and internal control scrolling keep page geometry within the viewport.

The new tests exercise face-local reversible smoothing with protected features/alpha, original byte preservation, stored processing fields and invalid-value rejection, shared export pixels, legacy zero defaults, overlay collapse, action-row alignment, background controls and undo, Crop-to-Library navigation, removed-photo recovery, scanner ranking/failed-interface chains/request preservation and no retry after transfer/cancel. Synthetic face boxes are injected for deterministic skin-mask tests; that does not certify real-world face detection or photographic retouching quality.

The expanded complete local suite passed **552 tests / 13 optional-fixture skips / no failures or errors**, with two existing Pillow warnings (296.14 s). The dedicated refinement suite passed **17 native tests**, including the final preview-fallback and layer-label checks. Earlier intermediate expectations were corrected to match the requested placement/automatic fallback behavior; regressions remain present.

The final frozen payload passed **40 workflow checks at each of 100% / 200% Windows scaling**, **25 document checks**, **31 stabilization checks**, and **8 synthetic crop-to-maker/bundled CPU-model checks**. A normal EXE startup was independently observed as maximized through Win32 `IsZoomed`. Runs used isolated data, a different cwd, a Python-free PATH and no external model override. The installer acceptance procedure verifies seven install/upgrade/uninstall, registration/shortcut, attribution/website, data-retention and installed-workflow checks; the release record supplies its executed result and the final hosted Windows run. Previous 3.3 results below remain historical. Physical scanner/printer and clean-machine acceptance remain separate.

## Coverage

The suite covers image preservation/EXIF, crop geometry, source/library persistence and migrations, editable masks/transforms/undo, precise parsed PDF geometry, quantities and pagination, layout bounds/overlap, customers/orders/reprints, backup/restore/reference-aware cleanup, export protection, optional preferences, Save/Discard/Cancel, manual orientation, scanner/helper request protocols, Copy/Print Set, NID crop handles and workspace controls.

Publication adds checks for visible About credits and inclusion of guides/attribution in the generated payload. Installer acceptance uses a synthetic workflow so the cleaned checkout does not depend on private demo photos. Missing private-demo and historical-release fixtures are reported as skips, not as verified cases.

## Previous verification

Before removal of private fixtures, 3.3.1 passed **544 tests**, no failures/errors/skips, with two existing Pillow warnings. Its supplied NID front and back scans were checked at three detector sizes; source and frozen actual-NID workflows passed **33 checks** at 100% and 200% Windows scaling. The 36-check portrait/joint workflow saved 69 photos in source and frozen runs. Those are historical results; the private files are deliberately absent now.

The pale NID fix combines contrast thresholds and small edge-gap closing on detection previews. Cropped outputs and the centered actual PDF were visually inspected. Original bytes stayed unchanged. Existing manual crops remain untouched until explicit re-detection or re-import.

## Recorded 3.3.2 release checks

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
