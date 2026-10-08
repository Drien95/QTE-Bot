@echo off
rem Fabrique dist\QTE-Bot-Setup-x.y.z.exe (installateur) et dist\QTE-Bot.zip : un dossier autonome (QTE-Bot.exe + modeles + config), sans Python a installer.
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
rem Installateur (Setup.exe) si Inno Setup 6 est installe : winget install JRSoftware.InnoSetup
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
for /f %%v in ('.venv\Scripts\python -c "import qte_bot; print(qte_bot.__version__)"') do set "VERSION=%%v"
if exist "%ISCC%" (
    "%ISCC%" /Q /DAppVersion=%VERSION% installer\QTE-Bot.iss || exit /b 1
    echo OK : dist\QTE-Bot-Setup-%VERSION%.exe
) else (
    echo Inno Setup absent : pas de Setup.exe ^(le zip suffit^).
)
echo OK : dist\QTE-Bot.zip
