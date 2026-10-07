@echo off
rem Premier lancement : cree le venv et installe les dependances. Ensuite : demarre directement.
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
    echo Installation...
    python -m venv .venv || (echo Python 3.10+ introuvable dans le PATH. & pause & exit /b 1)
    .venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || (echo Echec de l'installation. & pause & exit /b 1)
)
if "%~1"=="" (
    rem Menu sans console : fermer le panneau ferme tout. Erreurs dans qte_bot.log.
    start "" .venv\Scripts\pythonw.exe -m qte_bot.main
    exit /b 0
)
rem Avec option (--console, --label, --image) : la console sert a afficher les messages.
.venv\Scripts\python.exe -m qte_bot.main %*
pause
