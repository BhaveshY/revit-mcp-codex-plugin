---
name: setup-revit
description: Install, configure, or repair the Windows 11-only Revit MCP Next plugin for Autodesk Revit 2024 and Codex. Use when the user asks to connect Revit to Codex, install the Revit add-in or MCP bridge, configure the client, or complete first-run setup.
---

# Set Up Revit MCP Next

Use the companion repository `BhaveshY/revit-mcp-next`. Do not install the
legacy Revit MCP npm bridge for this plugin.

## Fast path

Require Windows 11, Revit 2024, Windows PowerShell, Node.js 24.x, and a disposable `.rvt`
file for the first write test.

Stop on macOS, Linux, WSL, or containers. Do not offer a non-Windows runtime
path; this plugin controls a local Windows desktop Revit process.

From a source checkout:

```powershell
npm install
npm run build
npm run build:addin
npm run install:windows -- -RevitYears 2024 -TrustRevitAlwaysLoad
npm run mcp:config -- -Client codex
npm run doctor:clients -- -Client codex
```

Prefer an extracted release installer when one is available. Never copy or
print `config\auth.env`; use the generated launcher/config output.

The plugin launcher resolves, in order:

1. `REVIT_MCP_NEXT_LAUNCHER`
2. `REVIT_MCP_NEXT_INSTALL_ROOT\launch-revit-mcp-next.cmd`
3. `%LOCALAPPDATA%\RevitMcpNext\launch-revit-mcp-next.cmd`
4. the Revit 2024 add-in install fallback

Restart Codex after install or plugin changes. Open Revit 2024 with a test
project, allow an add-in security prompt only after the user verifies its
source, then call `revit.status` followed by `revit.read_bundle`.

Revit 2025/2026 are not supported by the current Revit MCP Next package. Do not
install the Revit 2024/net48 add-in into those versions.

Normal daily use must not rerun installation or doctor commands. The plugin
wrapper hands off directly to the installed launcher.
