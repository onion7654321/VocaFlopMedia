# Vocaflop · Media Downloader

![Vocaflop logo](assets/logo.png)

A Windows desktop media downloader built with Python, Flet and yt-dlp. Download supported media in multiple video and audio formats, select quality, trim individual videos, and manage a download queue.

## Features

- Video, playlist and stream modes for supported sources: YouTube, SoundCloud, Niconico, X and Facebook.
- Import URL lists from TXT and edit a batch in a larger editor.
- Rename single-item outputs before download or rename a finished local file from its card.
- Stop, resume or cancel individual downloads or the entire queue.
- Download history, configurable concurrency and size limits, optional previews, and light/dark themes.
- Tool discovery and optional update checks for yt-dlp, FFmpeg and Deno.

SoundCloud supports audio output only. Bitrate options describe the encoder output, not the original source quality. Spotify, Vimeo, Bilibili and Threads downloads are not supported. Download only media you are authorized to save.

## Windows setup

1. Install 64-bit Python 3.11 or 3.12 and Git (optional for local use).
2. Run `install_windows.bat` to create the virtual environment and install pinned Flet packages.
3. Run `install_ffmpeg_windows.bat` and `install_deno_windows.bat` if these tools are missing. Install yt-dlp from its official GitHub release or use the application's update button. Alternatively, point Settings at existing tool folders.
4. Run `run_windows.bat`.

External executables are not included in this source archive. Configuration and history are stored in `%APPDATA%\Vocaflop`, outside the source folder. Browser cookies are optional; do not publish cookies, user settings or download history.

## Queue behavior

**Stop** interrupts running and queued jobs but preserves temporary files. Use Resume on a stopped card in the same app session. Resumption depends on the source, yt-dlp and stream type; live streams and interrupted conversions may restart. **Cancel** requires confirmation and removes only the job's temporary directory. **Clear** removes inactive cards without deleting finished files. Clear history takes effect without a confirmation and does not delete media. History cannot be cleared while jobs are running or stopped.

Enable **Settings → Downloads → Shut down computer after downloads** to power off Windows after every download in the current run succeeds. The switch is off on startup and a 60-second countdown can be cancelled from the footer. Failed, cancelled or stopped downloads block automatic shutdown. The app does not force-close other programs.

Click the name of an inactive single-video or audio card to edit its output filename. Press Enter or click outside to save. Playlist names are not used to rename all playlist outputs. Existing local files are never overwritten by the rename action.

## Development and distribution

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run `build_exe_windows.bat` on Windows, test the packaged application, then run `package_release_windows.bat` to create the portable ZIP and SHA-256 checksum in `release/`. Distribute the full one-folder build, not the EXE alone. See [BUILD_README.txt](BUILD_README.txt) for the build and GitHub release steps.

## Dependencies

[Flet](https://github.com/flet-dev/flet), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org/) and [Deno](https://github.com/denoland/deno) have their own licenses and distribution terms. If redistributing external binaries, include the applicable notices and meet their license obligations. A license for this project's own source code has not been selected.

### Download controls

- Choose a format and quality on the same row; the individual Download button appears after selecting quality. Batch downloads retain their shared or per-item defaults.
- Video: MP4, MKV, WebM, MOV, AVI. Audio: MP3, M4A, AAC, Opus, OGG, WAV, FLAC. Some formats require transcoding through FFmpeg; lossless export does not restore lost source detail.
- Click a title to edit the output filename; Enter or clicking outside commits it. Playlist entries keep their individual names.
- Click the links field to append newly copied supported URLs (duplicates are ignored). Native Ctrl+V and Windows clipboard history remain available.
- Click Play on the thumbnail to preview; Copy timestamp copies HH:MM:SS.

### Release 2.11.6

- Check that downloaded files still exist before opening their folder, including playlist and history entries.

### Release 2.11.5

- Unicode-safe output paths and confirmed replacement after successful download.
- Editing a title sets the next download filename without moving the previous file.
- Metadata refresh errors do not invalidate an available preview.

### Release 2.11.4

- High-contrast download completion notices in both themes.
- Cut validation messages clear when corrected, without clearing unrelated errors.
- Open folder from downloaded cards and history, using the actual output location.
- Verify output files before reporting a completed job; serialize history database access across worker threads.
- Portable Windows release archive and SHA-256 packaging helper.
