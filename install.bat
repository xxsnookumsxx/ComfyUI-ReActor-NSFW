@echo off
set "PYTHON_EXE=..\..\python_embeded\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=..\..\..\python_embeded\python.exe"
)

if not exist "%PYTHON_EXE%" (
    echo [ReActor] Embedded Python not found in parent directories, using system Python...
    set "PYTHON_EXE=python"
)

echo [ReActor] Using Python: %PYTHON_EXE%
"%PYTHON_EXE%" -s -m pip install -U pip
"%PYTHON_EXE%" install.py
pause
