# GitHub repository and release guide

This repository contains the application's source, tests, and documentation. Private photographs, application databases, generated output, local Python/tools, model weights, and packaged executables are excluded by `.gitignore`.

Project repository: [ovi2riyad/Printora](https://github.com/ovi2riyad/Printora). The repository name is Printora; the desktop application currently displays Studio Photo Maker.

## Upload the prepared repository

Use an existing repository URL or create an empty GitHub repository named `studio-photo-maker`. Private visibility is a sensible default for a studio project. If the local project already has a `.git` folder, do not initialize it again or replace its history.

With Git and GitHub CLI available in your terminal:

```powershell
gh auth login --hostname github.com --git-protocol https --web
```

Complete sign-in through GitHub's browser flow. Do not put access tokens in source files, terminal commands that will be shared, or chat messages. If commit identity is missing, set your preferred name and your GitHub-provided no-reply email in this repository:

```powershell
git config user.name "YOUR NAME"
git config user.email "YOUR GITHUB NO-REPLY EMAIL"
```

Review the actual staged file list before committing:

```powershell
git status --short
git diff --cached --stat
git diff --cached --name-only
```

If no initial commit exists yet, commit the reviewed source:

```powershell
git add .
git commit -m "Initial Studio Photo Maker source"
```

Then choose **one** of the following routes. The create command below creates a private repository and pushes the current local project:

```powershell
gh repo create YOUR-USERNAME/studio-photo-maker --private --source . --remote origin --push
```

For an existing **empty** repository, add its real URL and push instead:

```powershell
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

If `origin` or a remote history already exists, inspect it before changing anything. Do not force-push over existing work.

On the preparation PC, portable tools may be available at `.tools/git/cmd/git.exe` and `.tools/gh/bin/gh.exe`. They are local helpers, not part of the uploaded source. Add their directories to the current PowerShell session if needed:

```powershell
$env:PATH = (Join-Path (Get-Location) '.tools\git\cmd') + ';' + (Join-Path (Get-Location) '.tools\gh\bin') + ';' + $env:PATH
```

## What belongs in Git

- `app`, `tests`, `scripts`, `main.py`, batch files, and the PyInstaller specification.
- Dependency lists, project documentation, and `.github/workflows/tests.yml`.
- Deliberately selected non-private UI assets, if added in the future.

Keep `Demo`, `.tools`, `.venv`, `build`, `dist`, `output`, databases, credentials, and downloaded ONNX files outside Git history. Demo photographs must stay local even if the repository is private. Check new files before every push; ignore rules cannot remove sensitive content that has already been committed.

The project currently has no project-wide open-source license selected. Publishing source does not itself select a license. Third-party component/model notices are in `THIRD_PARTY.md`.

## Fresh-clone development

Install Python 3.12 x64. From the repository root, run `setup.bat`, then `run.bat`. The `.tools` runtime from the original workstation is not included in Git.

For the exact versions recorded in the tested environment, replace setup's package-install step with:

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
& '.\.venv\Scripts\python.exe' -m pytest -q -ra
```

Install the portrait model through Settings before background removal, or run the existing installer from the repository root:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.install_model
```

The installer downloads the model and verifies its expected checksum. The model stays in local application data. Do not commit it. See `PROJECT_INFO.md` for model lookup, packaging, storage, and full acceptance details.

## Automated checks

The Windows tests workflow runs for pushes, pull requests, and manual dispatch. It uses Python 3.12, pinned dependencies, headless Qt, and isolated application data. Its artifact contains the JUnit test report.

Private demo images and portrait models are not downloaded by CI. Cases that explicitly require the supplied demo images skip when those files are absent. CI does not replace the full local demo/model acceptance run or an actual-size physical printer check.

## Distribute the Windows application

Use a GitHub **Release asset** for an application ZIP, rather than committing `dist` or large model files to the source repository. Build locally with the portrait model installed, validate the frozen application, and ZIP the entire `dist/StudioPhotoMaker` folder including `_internal` and bundled third-party licenses. Upload that ZIP to a release only when you intend to distribute it.

The source archive alone is for developers; it does not contain the ready-to-run EXE or bundled model. Users of a packaged release do not need Python. The exact PDF footprint remains unchanged by hosting the code on GitHub.
