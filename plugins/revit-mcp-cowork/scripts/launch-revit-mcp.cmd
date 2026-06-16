@echo off
setlocal

set "MCP_CMD="
set "NPX_CMD="

if exist "%USERPROFILE%\.local\nodejs22\mcp-server-for-revit.cmd" set "MCP_CMD=%USERPROFILE%\.local\nodejs22\mcp-server-for-revit.cmd"
if not defined MCP_CMD if exist "%USERPROFILE%\.local\nodejs\mcp-server-for-revit.cmd" set "MCP_CMD=%USERPROFILE%\.local\nodejs\mcp-server-for-revit.cmd"
if not defined MCP_CMD for /f "delims=" %%I in ('where mcp-server-for-revit.cmd 2^>NUL') do (
  if not defined MCP_CMD set "MCP_CMD=%%I"
)

if defined MCP_CMD (
  "%MCP_CMD%"
  exit /b %ERRORLEVEL%
)

for /f "delims=" %%I in ('where npx.cmd 2^>NUL') do (
  if not defined NPX_CMD set "NPX_CMD=%%I"
)

if not defined NPX_CMD if exist "%USERPROFILE%\.local\nodejs22\npx.cmd" set "NPX_CMD=%USERPROFILE%\.local\nodejs22\npx.cmd"
if not defined NPX_CMD if exist "%USERPROFILE%\.local\nodejs\npx.cmd" set "NPX_CMD=%USERPROFILE%\.local\nodejs\npx.cmd"
if not defined NPX_CMD if exist "%ProgramFiles%\nodejs\npx.cmd" set "NPX_CMD=%ProgramFiles%\nodejs\npx.cmd"
if not defined NPX_CMD if exist "%ProgramFiles(x86)%\nodejs\npx.cmd" set "NPX_CMD=%ProgramFiles(x86)%\nodejs\npx.cmd"

if not defined NPX_CMD (
  echo Revit MCP startup error: npx.cmd not found. Install Node.js 22 LTS or add Node.js to PATH. 1>&2
  exit /b 127
)

"%NPX_CMD%" -y mcp-server-for-revit
exit /b %ERRORLEVEL%
