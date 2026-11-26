#!/usr/bin/env bash
set -euo pipefail
version="$1"
test "$(uname -m)" = x86_64
test -x dist/Vocaflop/Vocaflop
command -v desktop-file-validate >/dev/null
desktop-file-validate packaging/vocaflop.desktop
mkdir -p release build
stage=build/deb-stage
rm -rf "$stage"
mkdir -p "$stage/DEBIAN" "$stage/opt/vocaflop" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/pixmaps"
cp -a dist/Vocaflop/. "$stage/opt/vocaflop/"
cp packaging/vocaflop.desktop "$stage/usr/share/applications/"
cp assets/logo.png "$stage/usr/share/pixmaps/vocaflop.png"
ln -s /opt/vocaflop/Vocaflop "$stage/usr/bin/vocaflop"
cat > "$stage/DEBIAN/control" <<EOF
Package: vocaflop-media
Version: $version
Architecture: amd64
Maintainer: VocaFlopMedia <https://github.com/onion7654321/VocaFlopMedia>
Depends: libgtk-3-0, libmpv1, libsecret-1-0, ffmpeg
Description: Desktop media downloader
EOF
dpkg-deb --root-owner-group --build "$stage" "release/Vocaflop-$version-Linux-amd64.deb"
appdir=build/Vocaflop.AppDir
rm -rf "$appdir"
mkdir -p "$appdir/usr/bin"
cp -a dist/Vocaflop/. "$appdir/usr/bin/"
cp packaging/vocaflop.desktop "$appdir/"
ln -s Vocaflop "$appdir/usr/bin/vocaflop"
cp assets/logo.png "$appdir/vocaflop.png"
cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
HERE=$(dirname "$(readlink -f "$0")")
exec "$HERE/usr/bin/Vocaflop" "$@"
EOF
chmod +x "$appdir/AppRun"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 appimagetool "$appdir" "release/Vocaflop-$version-Linux-x86_64.AppImage"
tar -czf "release/Vocaflop-$version-Linux-x64.tar.gz" -C dist Vocaflop
