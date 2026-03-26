@echo off

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs -WindowStyle Normal"
    exit
)

set "ROOT=%~dp0"
set "FRONTEND=%ROOT%frontend"

if not exist "%FRONTEND%\dist\main.js" (
    echo Building for first time...
    cd /d "%FRONTEND%"
    call npx tsc -p tsconfig.electron.json
    call npx vite build
    if errorlevel 1 (
        echo Build failed!
        pause
        exit /b 1
    )
)

echo Starting App...
start /D "%FRONTEND%" "" npx electron .

timeout /t 3 /nobreak >nul
exit
