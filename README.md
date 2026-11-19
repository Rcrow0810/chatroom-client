# Chat Client

A desktop chat app (Python + Tkinter) with direct messages, a shared feed, games, a play-money wallet,
message translation, and Google Authenticator login.

> This repo is **only the client**. You need a chat server to connect to — the person who runs it will tell you
> its IP address.

## Download (easiest)

Go to the **[Releases](../../releases)** page, download the zip for your computer, unzip it, and run
`ChatClient` (`ChatClient.exe` on Windows). Type the server's IP at the top of the login window.

## Logging in

You need your password **and** a 6-digit code from the Google Authenticator app. On your first login a QR code
appears: in the app tap **+ → Scan a QR code**, then type the code it shows. Lost your phone? Ask the server's
owner to reset your authenticator.

## Run from source

Needs Python 3.10+ with Tkinter.

```bash
pip install -r requirements.txt
python3 login_app.py
```

Put two files from the server's owner next to `login_app.py`: **`chat.key`** (message key) and **`server.crt`**
(proves you're talking to the real server). They are not in this repo on purpose.

## Build the app yourself

Put `chat.key` and `server.crt` in this folder, then:

- Windows: double-click `build_windows.bat` → `dist\ChatClient\ChatClient.exe`
- Linux / macOS: `./build_unix.sh` → `dist/ChatClient/ChatClient` (Linux: `./install_linux.sh` adds it to your menu)

An app can only be built on the kind of computer it will run on. Both files get bundled **inside** the build, so
only share builds with people you want to be able to join your server.

## Optional extras

- **Translation** works over the internet out of the box. For offline translation: `pip install argostranslate langdetect`, then
  `python3 install_languages.py es fr de`. Not working? Run `python3 translator_check.py`.
- **On-screen accent keyboard**: the ⌨ button next to the emoji button.

## Security notes

- The client never talks to the database; everything goes through the server over an encrypted connection that only
  accepts the server's own certificate.
- The message key (`chat.key`) is shared by everyone on a server, so anyone with the app can read that server's messages.
