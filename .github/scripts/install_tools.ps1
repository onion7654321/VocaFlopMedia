param([ValidateSet('ffmpeg','deno')][string]$Tool)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:APPDATA 'Vocaflop\tools'
$tempFolder = Join-Path $env:TEMP ('Vocaflop-install-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tempFolder | Out-Null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    if ($Tool -eq 'ffmpeg') {
        $source = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
        $destination = Join-Path $root 'ffmpeg\bin'
        $names = @('ffmpeg.exe', 'ffprobe.exe')
    } else {
        $source = 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip'
        $destination = Join-Path $root 'deno'
        $names = @('deno.exe')
    }
    $zip = Join-Path $tempFolder 'tool.zip'
    Write-Host "Downloading $Tool from its official distributor..."
    Invoke-WebRequest -Uri $source -OutFile $zip -UseBasicParsing
    $unpack = Join-Path $tempFolder 'unpack'
    Expand-Archive -Path $zip -DestinationPath $unpack -Force
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    foreach ($name in $names) {
        $file = Get-ChildItem -LiteralPath $unpack -Filter $name -Recurse -File | Select-Object -First 1
        if (-not $file) { throw "$name not found in downloaded archive" }
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $destination $name) -Force
    }
    Write-Host "Installed to: $destination"
    Write-Host 'Reopen Vocaflop for the tool to be detected.'
} catch {
    Write-Host "Failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item -LiteralPath $tempFolder -Force -Recurse -ErrorAction SilentlyContinue
}
