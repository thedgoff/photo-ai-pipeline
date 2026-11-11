@echo off
echo =============================================
echo  AutoTag - AI Photo Tagging
echo =============================================
echo.

if "%~1"=="" (
    echo Drag a photo folder onto this file to tag it.
    echo.
    pause
    exit /b
)

python "%~dp0autotag.py" "%~1"

echo.
pause
