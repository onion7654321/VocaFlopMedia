# VocaFlop Media Downloader

![Vocaflop logo](assets/logo.png)

Desktop media downloader using Flet and yt-dlp. Download authorized media in video, playlist and stream modes, select formats and quality, trim clips, rename output files, and manage the queue and history.

## Download

Visit [GitHub Releases](https://github.com/onion7654321/VocaFlopMedia/releases). Windows x64 is the primary target; Linux x64 and macOS Intel/Apple Silicon packages are experimental until native testing is complete. Windows 32-bit is unsupported.

- Windows: Setup EXE or portable ZIP (extract the complete directory).
- Linux: AppImage, DEB or tar.gz; see system dependencies in [BUILDING.md](BUILDING.md).
- macOS: DMG, drag the app to Applications. Developer ID signing and notarization are not configured.

Tools are not bundled. Install missing yt-dlp, Deno and (on Windows) FFmpeg from the application's Update button, or select existing tools in Settings. On Linux/macOS install FFmpeg through the system package manager. See the build guide for details.

## Features

- Video: MP4, MKV, WebM, MOV, AVI. Audio: MP3, M4A, AAC, Opus, OGG, WAV, FLAC.
- Supported sources include YouTube, SoundCloud (audio only), Niconico, X and Facebook. Availability depends on the source and extractor version.
- Batch URLs, TXT import, quality selection, optional preview and timestamp copying.
- Stop/Resume/Cancel, queue concurrency limits, history and Open folder.
- Inline output filename editing; replacement requires confirmation.
- Optional automatic shutdown on Windows and systemd Linux, with a cancellable countdown.
- Light/dark themes and verified update downloads. Updates are installed manually.

## Development

Python 3.12 recommended. See [BUILDING.md](BUILDING.md) for setup, packaging and releases. See [CHANGELOG.md](CHANGELOG.md) for changes.

## Licensing

A source-code license has not been selected. Third-party components retain their respective licenses. Do not redistribute external binaries without meeting their license obligations. Download only media you are authorized to save.
