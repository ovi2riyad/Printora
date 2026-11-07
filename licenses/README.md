# Component licenses

Printora's own code, documentation and artwork use the root MIT `LICENSE`.
That license does not replace any component license.

The installer includes `packages/` with notices supplied by the installed runtime
distributions and their exact package metadata. Python's license is included too.
OpenCV and ONNX Runtime also carry notices under `_internal`. These are copied at
build time; they are not vendored dependencies in the source repository.

Qt/PySide6 and Qt PDF are used under their LGPLv3 option. `LGPL-3.0.txt` and its
incorporated `GPL-3.0.txt` are included here because some installed wheels only
carry their commercial alternative's notice. These libraries remain separate
dynamically loaded files in the complete application folder. Users may replace
them with compatible modified libraries; Printora imposes no restriction on
reverse engineering needed to debug those modifications.

Component source and build information:

- [Qt sources and versioned downloads](https://download.qt.io/official_releases/qt/)
- [Qt for Python source and releases](https://code.qt.io/cgit/pyside/pyside-setup.git/)
- [Qt PDF source](https://code.qt.io/cgit/qt/qtwebengine.git/)
- [Qt PDF licensing and PDFium attributions](https://doc.qt.io/qt-6/qtpdf-licensing.html)
- [PDFium source and license](https://pdfium.googlesource.com/pdfium/)
- [U²-Net source and Apache-2.0 license](https://github.com/xuebinqin/U-2-Net)
- [Python source and license](https://www.python.org/downloads/source/)

Use the shipped metadata and `requirements-lock.txt` to identify release versions;
the developer guide explains how to rebuild Printora. No Qt/PDFium source changes
are made by this project. PDFium's upstream BSD license is included here, and its
additional bundled-component terms are listed in Qt's attribution documentation.
The model's upstream Apache-2.0 license is included as `U2Net-Apache-2.0.txt`.
See `THIRD_PARTY.md` for the remaining projects and installer acknowledgements.
