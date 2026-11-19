#!/usr/bin/env bash
# Installs the built app for the current user and adds it to the Applications menu.
# Run ./build_unix.sh first.  To uninstall: delete ~/.local/opt/ChatClient and
# ~/.local/share/applications/chatclient.desktop
set -e
cd "$(dirname "$0")"

if [ ! -x dist/ChatClient/ChatClient ]; then
  echo "Can't find dist/ChatClient/ChatClient - run ./build_unix.sh first."
  exit 1
fi

DEST="$HOME/.local/opt/ChatClient"
mkdir -p "$HOME/.local/opt" "$HOME/.local/share/applications"
rm -rf "$DEST"
cp -r dist/ChatClient "$DEST"

cat > "$HOME/.local/share/applications/chatclient.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Chat Client
Comment=Chat room client
Exec=$DEST/ChatClient
Path=$DEST
Icon=utilities-chat
Terminal=false
Categories=Network;Chat;
DESKTOP
chmod +x "$HOME/.local/share/applications/chatclient.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Installed! Open the Applications menu (or press Super and type 'Chat Client')."
