"""Platform-specific desktop and release operations."""
import os
import platform
import shutil
import subprocess
from pathlib import Path


def system():
    return platform.system()


def architecture():
    machine = platform.machine().lower()
    if machine in ('amd64', 'x86_64'):
        return 'x64'
    if machine in ('arm64', 'aarch64'):
        return 'arm64'
    raise RuntimeError(f'Unsupported architecture: {machine}')


def ytdlp_asset():
    return {('Windows', 'x64'): 'yt-dlp.exe', ('Windows', 'arm64'): 'yt-dlp_arm64.exe',
            ('Linux', 'x64'): 'yt-dlp_linux', ('Linux', 'arm64'): 'yt-dlp_linux_aarch64',
            ('Darwin', 'x64'): 'yt-dlp_macos', ('Darwin', 'arm64'): 'yt-dlp_macos'}[(system(), architecture())]


def deno_asset():
    cpu = {'x64': 'x86_64', 'arm64': 'aarch64'}[architecture()]
    target = {'Windows': 'pc-windows-msvc', 'Linux': 'unknown-linux-gnu', 'Darwin': 'apple-darwin'}[system()]
    return f'deno-{cpu}-{target}.zip'


def open_directory(path):
    path = str(Path(path).resolve())
    if system() == 'Windows':
        os.startfile(path)
    else:
        command = 'open' if system() == 'Darwin' else 'xdg-open'
        subprocess.Popen([command, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def shutdown_command():
    if system() == 'Windows':
        return [str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'shutdown.exe'), '/s', '/t', '0']
    if system() == 'Linux' and shutil.which('systemctl'):
        return ['systemctl', 'poweroff']
    return None


def package_manager_hint():
    return 'brew install ffmpeg' if system() == 'Darwin' else 'Install ffmpeg using your distribution package manager (e.g. sudo apt install ffmpeg).'
