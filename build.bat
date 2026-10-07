@echo off
rem Fabrique dist\QTE-Bot.zip : un dossier autonome (QTE-Bot.exe + modeles + config), sans Python a installer.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m venv .venv || (echo Python 3.10+ introuvable dans le PATH. & exit /b 1)
)
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt pyinstaller || exit /b 1
.venv\Scripts\python -m pytest -q || (echo Tests en echec : pas de build. & exit /b 1)
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --onedir --name QTE-Bot QTE-Bot.pyw || exit /b 1
xcopy /e /i /q /y templates dist\QTE-Bot\templates >nul
copy /y config.json dist\QTE-Bot\config.json >nul
copy /y README.md dist\QTE-Bot\README.md >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\QTE-Bot -DestinationPath dist\QTE-Bot.zip"
echo.
echo OK : dist\QTE-Bot.zip
