VOCAFLOP 2.11.6 — WINDOWS BUILD AND GITHUB RELEASE

Build (Windows 10/11 x64)
1. Install Python 3.11 or 3.12 (64-bit).
2. Double-click install_windows.bat.
3. Double-click run_windows.bat and test the app with authorized media.
4. Double-click build_exe_windows.bat. It runs the unit tests and packages the app.
5. The output is dist\Vocaflop\Vocaflop.exe. Keep the entire dist\Vocaflop folder.
6. Test the packaged app on a clean Windows machine before publishing.
7. Run package_release_windows.bat to create release\Vocaflop-2.11.6-Windows-x64.zip and release\SHA256SUMS.txt.

PowerShell commands for a portable release archive (from project root):
  Compress-Archive -Path .\dist\Vocaflop -DestinationPath .\Vocaflop-2.11.6-Windows-x64.zip -Force

Tools are not bundled by the build script. Install them separately or configure existing tools in Settings. Official downloads:
  https://github.com/yt-dlp/yt-dlp/releases
  https://ffmpeg.org/download.html
  https://github.com/denoland/deno/releases
If you redistribute any external tools, comply with their license and notice requirements.

GitHub source repository
1. Create an empty repository at https://github.com/new (do not initialize README, .gitignore or license there).
2. Open PowerShell in the extracted project directory, then run:
  git init
  git add .
  git status
  git diff --cached --stat
  git commit -m "Initial public release"
  git branch -M main
  git remote add origin https://github.com/YOUR_USERNAME/Vocaflop.git
  git push -u origin main
3. Choose a license for your own source when ready; third-party terms still apply.
4. On GitHub, open Releases > Draft a new release. Create tag v2.11.6, give it a title, add release notes and upload the Windows ZIP from above. Publish the release after testing.

Do not commit credentials, cookies, personal settings, history, .venv, compiled caches or external binaries. The included .gitignore excludes common generated files. Review git status before committing.

Verification: 84 automated tests passed in the editing environment, including simulated downloader processes and archive packaging. Windows GUI, real media downloads, Flet packaging and the packaged executable still require Windows verification.

Pre-release smoke test
- On Windows, launch the EXE from the extracted release ZIP, without Python installed.
- Install or configure yt-dlp, FFmpeg, FFprobe and Deno. Test authorized MP4 and MP3 downloads.
- Enter invalid cut times, attempt download, correct the times and confirm both error messages disappear.
- Rename before downloading; verify the actual filename and Open folder from the card and History.
- Change the default folder after completion; Open folder must still open the original destination.
- Check Light/Dark themes, preview, timestamp copying, clipboard, Stop/Resume and Cancel.
- Verify shutdown remains off on launch; test the countdown and cancel action without letting the computer shut down.
- Check third-party license notices before redistributing tools. The portable ZIP is not an installer for the optional app-update manifest.
- Publish only after these checks pass. Consider marking the first build as a pre-release if it has not been tested on a clean machine.
