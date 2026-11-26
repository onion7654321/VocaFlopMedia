<div align="center">
  <img src="assets/logo.png" alt="VocaFlop logo" width="120">
  <h1>VocaFlop Media Downloader</h1>
  <p>Download, convert and organize media from a single desktop application.</p>

  [![Release](https://img.shields.io/github/v/release/onion7654321/VocaFlopMedia?include_prereleases&color=079355)](https://github.com/onion7654321/VocaFlopMedia/releases)
  [![Desktop distribution](https://github.com/onion7654321/VocaFlopMedia/actions/workflows/build.yml/badge.svg)](https://github.com/onion7654321/VocaFlopMedia/actions/workflows/build.yml)
  [![Downloads](https://img.shields.io/github/downloads/onion7654321/VocaFlopMedia/total?color=079355)](https://github.com/onion7654321/VocaFlopMedia/releases)
  ![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555555)

  **[Download](https://github.com/onion7654321/VocaFlopMedia/releases)** · [Build from source](BUILDING.md) · [Changelog](CHANGELOG.md) · [Report an issue](https://github.com/onion7654321/VocaFlopMedia/issues)
</div>

<!-- Add a current, sanitized application screenshot at docs/screenshot.png, then uncomment:
![VocaFlop desktop interface](docs/screenshot.png)
-->

## Download

Choose a package from the [Releases page](https://github.com/onion7654321/VocaFlopMedia/releases).

| Platform | Package | Installation |
| --- | --- | --- |
| Windows x64 | Setup EXE | Run the installer. |
| Windows x64 | Portable ZIP | Extract the entire archive, then launch Vocaflop.exe. |
| Linux x64 (experimental) | AppImage, DEB, TAR.GZ | Make the AppImage executable, install the DEB, or extract the archive. |
| macOS Intel (experimental) | Intel DMG | Open the image and drag the app into Applications. |
| macOS Apple Silicon (experimental) | ARM64 DMG | Open the image and drag the app into Applications. |

Windows is the primary target. Linux and macOS packages require native runtime validation; a successful CI build alone does not establish compatibility. Windows 32-bit is not supported. Installers are unsigned; macOS notarization is not configured.

## Features

- Batch URL entry, TXT import, video, playlist and stream modes.
- Video output: MP4, MKV, WebM, MOV and AVI.
- Audio output: MP3, M4A, AAC, Opus, OGG, WAV and FLAC.
- Quality selection, clip trimming, inline output filenames and confirmed file replacement.
- Optional media preview with timestamp copying.
- Individual and batch Stop, Resume and Cancel controls, configurable concurrency and download limits.
- Local history and Open folder, with checks for missing downloaded files.
- Light and dark themes, tool discovery and update checks.
- Optional automatic shutdown on Windows and systemd Linux after successful downloads, with a cancellation window.

Supported sources include YouTube, SoundCloud (audio only), Niconico, X and Facebook. Availability varies with source restrictions and yt-dlp versions. Audio bitrate is an output encoding setting, not a guarantee of source quality.

## Getting started

1. Launch VocaFlop and configure a download folder in Settings.
2. Install or locate the required media tools (see below).
3. Paste URLs, select an output format and quality, and optionally set a filename or clip range.
4. Start the download and use Open folder to locate the completed file.

### Media tools

External executables are not bundled. VocaFlop uses [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg and FFprobe](https://ffmpeg.org/) and [Deno](https://deno.com/). Use the application's tool update controls or specify installed tool locations in Settings. On Linux and macOS, install FFmpeg using your package manager.

For Ubuntu-based systems, install the relevant runtime libraries as described in [BUILDING.md](BUILDING.md). On macOS with Homebrew, `brew install ffmpeg` installs FFmpeg and FFprobe. On Windows, the application's tools updater can install FFmpeg.

## Troubleshooting

- **Download or extraction fails:** check tool availability and update yt-dlp; confirm the source is supported and accessible.
- **Missing FFprobe:** install FFmpeg and FFprobe together and verify their locations in Settings.
- **Preview unavailable:** some sources do not provide a usable direct preview; download authorized media to play locally.
- **Cannot resume:** some sources, live streams and conversion stages require restarting a download.

Include the OS, app version and sanitized error details when [reporting a bug](https://github.com/onion7654321/VocaFlopMedia/issues/new/choose). Never share cookies, access tokens or private URLs.

## Development

Python 3.12 is recommended. From the repository root, create a virtual environment, activate it, then run:

```sh
python -m pip install -e ".[build,dev]"
python -m unittest discover -s tests -q
python main.py
```

Native packaging uses `python scripts/build.py`. See [BUILDING.md](BUILDING.md) for prerequisites, CI and the tag-based release process. See [CONTRIBUTING.md](CONTRIBUTING.md) for reporting issues and proposing changes.

## Privacy and security

Settings and download history are stored locally under the application's data directory. Downloads, metadata lookups and update checks involve external network services. Optional browser cookies may contain sensitive authentication data. Do not commit settings, cookies, history or downloaded media. See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Licensing and responsible use

A source-code license has not yet been selected. Public access to this repository does not by itself grant permission to redistribute or modify its code. Third-party components retain their respective licenses. See [THIRD_PARTY.md](THIRD_PARTY.md).

Download only media you have permission to access and save, and comply with applicable laws and service terms. VocaFlop is not affiliated with the media platforms listed above.
