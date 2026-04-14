@echo off
REM ============================================================
REM import_database.bat - Importa database.js (WorkNC) nel DB
REM ============================================================
setlocal
cd /d "%~dp0"

set "JS_PATH=%~1"
if "%JS_PATH%"=="" set "JS_PATH=.\database.js"

echo.
echo   ==========================================
echo    Import database.js (WorkNC) -^> DB
echo   ==========================================
echo.

if not exist "%JS_PATH%" (
    echo   X File non trovato: %JS_PATH%
    echo   Uso: import_database.bat [path\database.js]
    exit /b 1
)

REM Trova Python
set "PYTHON="
if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"
if "%PYTHON%"=="" (
    where python >nul 2>&1 && set "PYTHON=python"
)
if "%PYTHON%"=="" (
    where py >nul 2>&1 && set "PYTHON=py"
)
if "%PYTHON%"=="" (
    echo   X Python non trovato
    exit /b 1
)

echo   Python   : %PYTHON%
echo   Sorgente : %JS_PATH%
echo.

"%PYTHON%" importers\import_from_database_js.py "%JS_PATH%"
if errorlevel 1 (
    echo.
    echo   X Import fallito
    exit /b 1
)

echo.
echo   OK Import completato
echo.
endlocal
