# Revit MCP Cowork

Use this plugin to connect Codex Desktop on Windows to Autodesk Revit 2024 through the `mcp-server-for-revit` bridge.

## Install Contract

The repo is a Codex plugin marketplace. Users install it with:

```powershell
codex plugin marketplace add https://github.com/BhaveshY/revit-mcp-codex-plugin
codex plugin add revit-mcp-cowork@revit-mcp-codex-plugin
```

After install, tell the user to fully quit and reopen Codex Desktop.

The Codex install only registers the plugin and MCP server. The Windows machine also needs:

- Revit 2024.
- Node.js 22 LTS recommended. Node 20+ is supported, but Node 22 is the tested path.
- `npm install -g mcp-server-for-revit`.
- The Revit MCP addin installed in `%AppData%\Autodesk\Revit\Addins\2024\`.
- Revit open with a project document loaded and the listener started.

For a fresh Windows PC, direct the user to run the repo helper after cloning:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows-codex-desktop.ps1
```

## MCP Launch Behavior

Codex registers the MCP server as:

```text
cmd /c .\scripts\launch-revit-mcp.cmd
```

The launcher prefers a global `mcp-server-for-revit.cmd`, then falls back to `npx -y mcp-server-for-revit`. It checks PATH, `%USERPROFILE%\.local\nodejs22`, `%USERPROFILE%\.local\nodejs`, and standard Program Files Node.js locations.

## First Action In A Revit Session

Always run the setup health check before model work:

1. Use `send_code_to_revit` with the non-blocking health-check snippet from `setup-revit`.
2. Call `get_current_view_info`.
3. Report the document, active view, Revit version, and whether the bridge is live.

Never call `say_hello`; upstream opens a blocking modal Revit dialog.

## Safety Rules

- Use explicit high limits on listing/filtering tools to avoid silent caps.
- Do not use a filtered result length as the authoritative model count. Cross-check counts with `analyze_model_statistics` or `send_code_to_revit`.
- Bracket destructive actions with before/after snapshots.
- Review custom C# before sending it to Revit, and wrap modifications in a Revit transaction.
- Treat Chinese error text or `Success: false` responses as errors, not data.

## Common Failure Interpretation

- MCP server missing: Node is absent, PATH is stale, or `mcp-server-for-revit` is not installed.
- Node 24 install failure: install Node 22 LTS and rerun `npm install -g mcp-server-for-revit`.
- Tools listed but calls time out: Revit is closed, no project is loaded, the listener is stopped, or Revit has a modal dialog open.
- Plugin installed but not visible: fully quit and reopen Codex Desktop.
