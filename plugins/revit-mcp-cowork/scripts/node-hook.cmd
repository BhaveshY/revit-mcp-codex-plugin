@echo off
setlocal

set "NODE_EXE="

for /f "delims=" %%I in ('where node.exe 2^>NUL') do (
  if not defined NODE_EXE set "NODE_EXE=%%I"
)

if not defined NODE_EXE if exist "%USERPROFILE%\.local\nodejs22\node.exe" set "NODE_EXE=%USERPROFILE%\.local\nodejs22\node.exe"
if not defined NODE_EXE if exist "%USERPROFILE%\.local\nodejs\node.exe" set "NODE_EXE=%USERPROFILE%\.local\nodejs\node.exe"
if not defined NODE_EXE if exist "%ProgramFiles%\nodejs\node.exe" set "NODE_EXE=%ProgramFiles%\nodejs\node.exe"
if not defined NODE_EXE if exist "%ProgramFiles(x86)%\nodejs\node.exe" set "NODE_EXE=%ProgramFiles(x86)%\nodejs\node.exe"

if not defined NODE_EXE (
  echo Revit MCP hook error: node.exe not found. Install Node.js 22 LTS or add Node.js to PATH. 1>&2
  exit /b 127
)

"%NODE_EXE%" %*
exit /b %ERRORLEVEL%
