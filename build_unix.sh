#!/usr/bin/env bash
# Builds ChatClient as a desktop app on Ubuntu/Linux (or macOS).  Run it ON that computer.
# Result: dist/ChatClient/ChatClient
set -e
cd "$(dirname "$0")"

# These two files come from whoever runs the chat server. They are NOT in the GitHub repo.
for f in chat.key server.crt; do
  [ -f "$f" ] || { echo "Missing $f - copy it from your chat server into this folder, then run again."; exit 1; }
done

# A private Python environment, so nothing touches the system Python
# (newer Ubuntu refuses plain "pip install" outside one).
python3 -m venv .buildenv
source .buildenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --clean --windowed --name ChatClient \
  --collect-submodules qrcode \
  --add-data "chat.key:." \
  --add-data "server.crt:." \
  login_app.py

echo
echo "Build done!  Next, run:  ./install_linux.sh"
