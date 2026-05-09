@echo off
REM Run thesis-stage offline experiments.

set PYTHON_CMD=python
python --version >nul 2>&1
if errorlevel 1 (
    py -3 --version >nul 2>&1
    if errorlevel 1 (
        echo Failed. Python 3.9+ was not found.
        pause
        exit /b 1
    )
    set PYTHON_CMD=py -3
)

%PYTHON_CMD% run_paper_experiments.py
if errorlevel 1 (
    echo.
    echo Failed. Please install dependencies first:
    echo pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo Done. Please check the output directory.
pause
