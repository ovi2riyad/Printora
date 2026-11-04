# Third-party components

The application uses Python (PSF), PySide6/Qt (LGPLv3/GPLv3/commercial terms; this application uses dynamically linked libraries), Pillow (HPND), OpenCV (Apache-2.0), ONNX Runtime (MIT), NumPy (BSD-3-Clause), and ReportLab (BSD). Development tools include pytest, pypdf, and PyInstaller. Their installed distributions carry the authoritative licenses. Retain bundled license files when redistributing the executable folder.

The `u2net_human_seg.onnx` portrait model and optional `u2netp.onnx` lightweight fallback come from the [rembg project release](https://github.com/danielgatis/rembg/releases/tag/v0.0.0). U²-Net originates from [xuebinqin/U-2-Net](https://github.com/xuebinqin/U-2-Net) (Apache-2.0). Model weights are excluded from the Git source repository. Settings and the installer can download them explicitly; a Windows application build bundles the installed portrait model when available at build time. See the upstream projects for model details and licenses.

The development-only face test image `.tools/face-test.jpg` was downloaded from OpenCV's sample data to validate detection and segmentation; it is not included in the application or distributable. Synthetic images are used in the automated test suite.
