# Build and release

## Development

From the repository root, create a virtual environment with Python 3.12:

```sh
python -m venv .venv
```

Activate with `.venv\Scripts\activate.bat` in Windows CMD, or `source .venv/bin/activate` on Unix. Then:

```sh
python -m pip install -e ".[build,dev]"
python -m unittest discover -s tests -q
python main.py
```

## Native packaging

Build on the target OS and architecture. Windows x64 requires Inno Setup 6.4+ (ISCC on PATH or installed in the default directory). Ubuntu 22.04 x64 requires `libgtk-3-0 libmpv1 libsecret-1-0 ffmpeg`, dpkg-deb, and appimagetool on PATH. AppImage still requires host multimedia/desktop libraries; this is not a fully self-contained Linux image. macOS requires Xcode command-line tools and FFmpeg (`brew install ffmpeg`). Install yt-dlp and Deno through the app or their official distributors. Windows can install FFmpeg and Deno through the app; external binaries are not bundled in installers.

```sh
python scripts/build.py
```

Output is in `release/`. `--package-only` reuses an existing native `dist/` build; do not reuse stale builds across releases. Keep release/ clean before packaging. The Windows installer installs per user, creates Start Menu shortcuts, offers an optional desktop shortcut, and does not delete user downloads/history on uninstall.

## GitHub Actions

Run **Desktop distribution** manually from Actions for test builds. The workflow builds Windows x64, Linux x64, macOS Intel and macOS ARM64. **Source checks** runs tests, lint, dependency consistency and vulnerability scanning on pushes and pull requests. Findings must be reviewed; an audit is not a security certification.

For release, update `app/__init__.py` (the single version source), commit and push. After CI succeeds:

```sh
git tag v2.13.0
git push origin v2.13.0
```

The tag workflow verifies version consistency, packages all four targets, aggregates SHA256SUMS.txt and creates a draft GitHub release. Review the artifacts and run native smoke tests before publishing. The app checks published stable GitHub releases by default; a custom HTTPS manifest can override this. It downloads checksum-verified updates but never executes them automatically. An unsigned checksum is integrity checking, not publisher authentication. Windows signing and macOS Developer ID signing/notarization must be arranged separately.

## Smoke test

On each OS: launch from installed location; verify tool discovery and updates; download permitted MP4 and MP3; test rename/replace, trim, pause/resume/cancel, history/open folder, preview, theme switching, and uninstall. Check shutdown cancellation without issuing a real shutdown. Verify files against SHA256SUMS.txt. Do not publish untested packages as stable.

## Migrating from 2.12

Remove the six obsolete root BAT scripts and BUILD_README.txt from Git (they are not deleted by copying the new ZIP over an existing checkout). Keep .git and any local user data. Replace the existing build workflow, then commit with `git add -A`.
