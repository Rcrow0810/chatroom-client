@echo off
REM Builds ChatClient as a double-click Windows app.  Run this on a Windows PC
REM (an app can only be built on the kind of computer it will run on).
REM Result: dist\ChatClient\ChatClient.exe

for %%F in (chat.key server.crt) do if not exist %%F (
  echo Missing %%F - copy it from your chat server into this folder, then run again.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt pyinstaller || goto :error
python -m PyInstaller --noconfirm --clean --windowed --name ChatClient ^
  --collect-submodules qrcode ^
  --add-data "chat.key;." ^
  --add-data "server.crt;." ^
  --add-data "icon.png;." ^
  --add-data "icon.ico;." ^
  --icon icon.ico ^
  login_app.py || goto :error

echo.
echo Done!  Your app is in dist\ChatClient  (zip that whole folder to share it).
pause
exit /b 0

:error
echo.
echo Build failed - read the messages above.
pause
exit /b 1
