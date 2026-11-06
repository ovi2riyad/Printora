# Studio Photo Maker 3.0 — validation results

Executed on Windows, 2026-11-06, Python 3.12.10 x64. These are recorded checks, not guarantees for later changes. Core phases were tested/fixed sequentially. The subsequent Printora 3.1 update adds Phase 6 and the requested Windows installer.

## Printora 3.1 tools and Windows Setup

Initial expanded suite: **81 passed, 2 existing warnings, 19.78 seconds** (`.tools/printora-31-tests.xml`). Initial source acceptance: **36 checks, 68 photos, exit 0, 46.42 seconds**, in fresh `.tools/printora-31-source-data`; results under `.tools/printora-31-source-check`. Seven new tests cover contact-sheet pagination/privacy, QR roundtrip/strict parsing, receipt privacy/price validation, exact calibration geometry, isolated batch failures/source hashes/review defaults, actual Qt review/save/lookup/preferences/statistics, and production installer directives.

The clean onedir build and first production installer compile succeeded. Inno Setup 7.1.1 was downloaded from its official immutable GitHub release, checked against SHA-256 `8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0`, and its Authenticode signature reported Valid (Pyrsys B.V.). Production Setup uses 64-bit Program Files with administrator privileges, common Desktop/Start menu shortcuts and a stable Windows uninstall registration. Data remains under the existing per-user StudioPhotoMaker folder.

Final suite after the review-layout adjustment: **81 passed, 2 existing warnings, 22.30 seconds**, `.tools/printora-31-final-tests.xml`. Final source acceptance passed **36 checks, 68 photos, exit 0, 71.70 seconds** with fresh data; `.tools/printora-31-final-source-check/result.json`. That run overlapped installer compression; timing is not a performance guarantee.

The final clean onedir build succeeded (`.tools/printora-31-final-build.log`). The actual installed `Printora.exe` passed **36 checks with 68 photos, exit 0, 51.61 seconds**, with fresh app data, no external model override and only its bundled model. Full installer harness passed in **222.25 seconds**, including compiler time, installation, upgrade, dashboard smoke, full workflow and uninstall. Evidence: `.tools/printora-31-final-install-check/result.json`, `install.log`, `upgrade.log`, `uninstall.log`, `workflow/result.json`, screenshots and PDFs.

Verified actual Desktop/Start menu shortcut targets/working directories, Windows Installed Apps registration/version, stable upgrade identity, renamed EXE startup without Python, retained user-data sentinel and unknown application-folder file through upgrade/uninstall, removal of installed binaries/shortcuts/registration, and all original workflow/source hashes. The uninstaller intentionally leaves the unknown-file directory, and the preservation assertion passed. All three previous release EXE hashes remain unchanged (`.tools/printora-31-previous-releases.json`). The validated portable package was promoted separately to `dist/Printora-3.1`.

The harness uses the same installer source with a separate test identity, workspace destinations and non-admin privileges. Production Setup defaults to `{commonpf64}\Printora` (normally `C:\Program Files\Printora`), requires administration and creates common shortcuts. Those directives were checked and the production Setup compiled. A real elevated Program Files install was **not** executed in this non-admin automation session. Physical printer/ruler validation remains outstanding. The final deliverable is `dist/installers/Printora-3.1.0-Setup.exe`; source is pushed separately from binary release publishing. All 3.0 results below are historical baseline evidence.

The 3.1 source update is uploaded to `main`; current hosted results are visible under [Windows tests](https://github.com/ovi2riyad/Printora/actions/workflows/tests.yml). A clean hosted checkout is expected to run 77 tests and skip four excluded private/local fixtures; inspect the actual run before claiming demo/model/installer acceptance occurred there. The local installed-app acceptance above is separate evidence.

## Automated tests

**Final suite: 74 passed, 2 existing warnings, 30.38 seconds.** Command:

```powershell
& '.\.tools\python\python.exe' -m pytest -q --junitxml=.tools/v3-final-tests.xml
```

The warnings are Pillow `getdata` deprecations in the existing synthetic composition test. This run overlapped release acceptance on the development workstation; timing is not a performance guarantee.

| Milestone | Passing tests | Recorded seconds |
|---|---:|---:|
| Pre-3.0 baseline | 57 | 18.20 |
| Phase 1 selection/composition | 60 | 13.62 |
| Phase 2 customers | 62 | 17.85 |
| Phase 3 orders, including Qt reprint flow | 65 | 16.02 |
| Phase 4 multi-photo sessions | 68 | 16.59 |
| Final core/editor/recipe/integration suite | 74 | 30.38 |

Coverage preserves exact PDF millimetre geometry, borders, pagination, mixed sizes, copy identity/overlap/bounds, original/EXIF safety, perspective crops, real Qt transforms/brushes/selection, durable serials, source deduplication, legacy jobs/profiles/library migration, source release-copy migration, settings and verified storage checks.

New checks cover persistent selection across views/search, Balanced margins, nullable dates, Unicode/international/alternate/empty mobiles, shared-number handling, archive/recovery, source-to-crop association/reconciliation/unlink, immutable historical snapshots, filtered mobile-search reprint UI, export failure/recovery markers, restored orders/PDFs, five-person mixed-size quantities, orientation/ties/manual override, manual placement/session retention, source-job preservation, recipes/IDs, brush opacity/hardness, group transforms, linked-job UPSERT, transactional DDL rollback, future-schema refusal and order-only cache references.

## Full source acceptance

**Passed: 29 workflow checks, 68 prepared photos, exit 0, 146.20 seconds.** Final source and frozen acceptance ran concurrently in separate fresh data directories. An earlier isolated source run passed the same expanded 29 checks in 48.26 seconds; neither timing is a hardware-independent promise.

| Private input | Prepared photos |
|---|---:|
| IMG_0007.jpg | 9 |
| IMG_0008.jpg | 11 |
| IMG_0009.jpg | 18 |
| portrait (1).jpg | 8 |
| portrait (2).jpg | 9 |
| portrait (3).jpg | 9 |
| Four combined joint examples | 4 |
| **Total** | **68** |

The actual application workflow checked persistent sources/crops/serials, combined/separate joint inputs, offline segmentation/fine edges, manual mask/tone settings, all layout modes, quantities retaining coordinates, profiles/settings, removed-photo recovery, restart/lazy loading, exact PDFs, unchanged original hashes and cross-path backup/restore.

The 3.0 extension additionally exercised optional customer assignment on deduplicated import, balanced framing controls, grouped transforms/opacity, full recipes, a five-composition 22-copy session, manual session placements/reopen, immutable contacts/compositions, mobile/order history, a changed 24-copy reprint and successful reprint after restoring customer/order/session data to another path. Customer contact fixtures are synthetic.

Visual review included the dashboard, editor framing/selection, library, mixed print sheets, customer/order pages and output images. An unsafe diagnostic manual move was rejected by overlap validation and the fixture was corrected to use a valid position; no production layout validation was weakened.

## Standalone Windows package

Clean PyInstaller process exited **0**. The candidate contained the **175,997,641-byte** portrait model and passed full acceptance with fresh app data and **no external model override**: **29 checks, 68 photos, exit 0, 146.19 seconds**.

The validated candidate was promoted separately to:

```text
dist/StudioPhotoMaker-v3/StudioPhotoMaker.exe
```

Both older release EXE hashes were checked unchanged: `dist/StudioPhotoMaker-v2` and `dist/StudioPhotoMaker`. The whole 3.0 folder, including `_internal`, is required; no system Python is needed. Current documentation/attributions are copied alongside the package after verification.

Local evidence remains excluded from Git:

- `.tools/v3-final-tests.xml`
- `.tools/v3-final-build.log`
- `.tools/v3-delivery-check/result.json` and source screenshots/PDFs
- `.tools/v3-frozen-check/result.json` and frozen screenshots/PDFs
- `.tools/v3-previous-releases.json`
- Fresh isolated data under `.tools/v3-delivery-data` and `.tools/v3-frozen-data`

## GitHub and clean-checkout checks

The Windows workflow uses pinned dependencies, offscreen Qt with the Windows font directory, and isolated app data. Three private-demo cases and one prior-release-data-copy case skip when their excluded fixtures are absent; those skips do not count as demo/model validation on GitHub.

Hosted Windows run [42165424889](https://github.com/ovi2riyad/Printora/actions/runs/42165424889) passed for implementation commit `9e0e3eed5b7467d8d7cac2c130be3538f7229a53`: **70 passed, 4 skipped, 0 failures/errors**, JUnit suite time **21.466 seconds**. The skips are the three private portrait-sheet cases and the previous-release local data-copy case. The JUnit artifact was downloaded and inspected. A local run with the same Windows-font setting also passed all 74 tests.

All 45 staged text/source files were reviewed for private/generated paths, unexpectedly large files and common credential signatures. Private images/customer information, tools, databases, model weights, build output, backups and diagnostic artifacts remained excluded. Source publishing does not itself publish a binary GitHub Release. Documentation-only completion commits do not change the validated implementation.

## Remaining physical and product limits

No physical printer was available: print at Actual Size / 100%, measure with a ruler and check driver margins. Segmentation/cropping/head placement remain source-dependent and can need manual correction. Face boxes are not person-count or document-compliance guarantees. External assets altered outside the application can affect path-based historical renders; retain app-managed assets/backups.

No HEIC/RAW/PSD, nested Photoshop groups, independent history panel, transparent-cutout export, mid-inference cancellation or arbitrary nesting optimizer. Optional Phase 6 contact sheets/QR/receipts/batch/statistics/calibration expansion remain follow-up work. No new core dependency or cloud processing was introduced.
