#!/bin/sh
# EL-FETCH installer for Linux (x86_64). No root needed.
#
#   curl -fsSL https://raw.githubusercontent.com/a7knsh/EL-FETCH/main/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/a7knsh/EL-FETCH/main/install.sh | sh -s -- --uninstall
#
# Installs to ~/.local/share/elfetch, adds an application-menu entry and the `elfetch` command (~/.local/bin).
set -eu

REPO="a7knsh/EL-FETCH"
ASSET="EL-FETCH-linux-x86_64"
DIR="${XDG_DATA_HOME:-$HOME/.local/share}/elfetch"
BIN="$HOME/.local/bin/elfetch"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications/elfetch.desktop"
ICON="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps/elfetch.png"

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$DIR" "$APPS" "$ICON"
    [ -L "$BIN" ] && rm -f "$BIN"
    echo "EL-FETCH removed. (Your settings in ~/.config/elfetch were kept.)"
    exit 0
fi

[ "$(uname -s)" = Linux ] || { echo "This script is for Linux. On Windows use EL-FETCH-Setup.exe from the releases page." >&2; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo "Only x86_64 builds are available. Install from source instead (see README)." >&2; exit 1; }

URL="https://github.com/$REPO/releases/latest/download/$ASSET"
mkdir -p "$DIR"
echo "Downloading $URL"
if command -v curl >/dev/null 2>&1; then
    curl -fL --progress-bar -o "$DIR/EL-FETCH.new" "$URL"
else
    wget -q --show-progress -O "$DIR/EL-FETCH.new" "$URL"
fi
chmod +x "$DIR/EL-FETCH.new"
mv -f "$DIR/EL-FETCH.new" "$DIR/EL-FETCH"

"$DIR/EL-FETCH" install

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "Note: add ~/.local/bin to your PATH to use the \`elfetch\` command in a terminal." ;;
esac
echo "Done. Start EL-FETCH from your application menu, or run: elfetch"
