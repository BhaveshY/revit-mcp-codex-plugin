# Windows Codex Desktop Install

Use this guide to install the Revit MCP Codex plugin on a Windows PC using the GitHub repo as the Codex marketplace source.

## Supported Setup

- Windows 10 or 11.
- Codex Desktop with the `codex` CLI available in PowerShell.
- Autodesk Revit 2024.
- Node.js 22 LTS recommended. Node.js 20+ is supported.
- Internet access for GitHub, nodejs.org, and npm.

Node 24 is not recommended for first-time setup because the MCP server currently depends on `better-sqlite3`, which can require local C++ build tools on Node 24. Node 22 LTS has working prebuilt binaries in the tested setup.

## Option A: Full Bootstrap From This Repo

Clone the repo and run the Windows bootstrap script:

```powershell
git clone https://github.com/BhaveshY/revit-mcp-codex-plugin.git
cd revit-mcp-codex-plugin
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows-codex-desktop.ps1
```

The script does four things:

1. Installs Node 22 under `%USERPROFILE%\.local\nodejs22` if that user-local Node install is missing.
2. Installs the npm bridge with `npm install -g mcp-server-for-revit`.
3. Installs the Revit 2024 addin from the upstream `mcp-servers-for-revit` v1.0.0 release into `%AppData%\Autodesk\Revit\Addins\2024\`.
4. Adds this GitHub repo as a Codex plugin marketplace and installs `revit-mcp-cowork`.

After the script finishes, fully quit and reopen Codex Desktop.

## Option B: Manual Install

### 1. Install the Codex plugin from the repo link

```powershell
codex plugin marketplace add https://github.com/BhaveshY/revit-mcp-codex-plugin
codex plugin add revit-mcp-cowork@revit-mcp-codex-plugin
```

You can also use the shorter owner/repo source:

```powershell
codex plugin marketplace add BhaveshY/revit-mcp-codex-plugin
```

### 2. Install Node 22 LTS

Install Node.js 22 LTS from https://nodejs.org, or use a user-local install under:

```text
%USERPROFILE%\.local\nodejs22
```

Close and reopen Codex Desktop after changing PATH.

### 3. Install the npm Revit MCP server

```powershell
npm install -g mcp-server-for-revit
```

The plugin launcher prefers this global binary. If it is missing, it falls back to:

```powershell
npx -y mcp-server-for-revit
```

### 4. Install the Revit 2024 addin

Download the Revit 2024 ZIP from:

```text
https://github.com/mcp-servers-for-revit/mcp-servers-for-revit/releases/tag/v1.0.0
```

Extract the ZIP and copy the extracted addin files into:

```text
%AppData%\Autodesk\Revit\Addins\2024\
```

The folder should contain one or more `.addin` files and a `revit_mcp_plugin` or equivalent addin payload folder.

### 5. Start Revit and the bridge

1. Start Revit 2024.
2. If Revit asks whether to load the addin, choose `Always Load`.
3. Open a project or create a blank project.
4. Find the Revit MCP panel and click `Start Listening`.
5. Open Codex Desktop and ask: `Run a Revit health check.`

## Verify The Codex Side

These commands should show the plugin and MCP registration:

```powershell
codex plugin list --json
codex mcp get revit
```

Expected MCP command:

```text
cmd /c .\scripts\launch-revit-mcp.cmd
```

## Troubleshooting Short List

- If Codex cannot see the plugin, fully quit and reopen Codex Desktop.
- If the MCP server does not start, run `node --version` and `npm list -g mcp-server-for-revit`.
- If Node 24 fails while installing `better-sqlite3`, install Node 22 LTS and rerun `npm install -g mcp-server-for-revit`.
- If tools are visible but calls time out, Revit is usually closed, no project is loaded, or the addin listener is stopped.
- Do not use `say_hello`; it opens a blocking Revit dialog. Use `Run a Revit health check.`
