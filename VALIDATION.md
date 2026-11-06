# Studio Photo Maker 3.0 — validation results

Executed on Windows, 2026-11-06, Python 3.12.10 x64. These are recorded checks, not guarantees for later changes. Core phases were tested/fixed sequentially; optional Phase 6 extras were not implemented.

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

Hosted results are recorded after the reviewed source push. Source review excludes private images/customer information, tools, databases, model weights, build output, backups and credentials. Source publishing does not itself publish a binary GitHub Release.

## Remaining physical and product limits

No physical printer was available: print at Actual Size / 100%, measure with a ruler and check driver margins. Segmentation/cropping/head placement remain source-dependent and can need manual correction. Face boxes are not person-count or document-compliance guarantees. External assets altered outside the application can affect path-based historical renders; retain app-managed assets/backups.

No HEIC/RAW/PSD, nested Photoshop groups, independent history panel, transparent-cutout export, mid-inference cancellation or arbitrary nesting optimizer. Optional Phase 6 contact sheets/QR/receipts/batch/statistics/calibration expansion remain follow-up work. No new core dependency or cloud processing was introduced.
