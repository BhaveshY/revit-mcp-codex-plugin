---
name: setup-revit
description: Use when the user asks to "set up Revit", "install the Revit plugin", "connect Revit to Claude", "configure the Revit MCP", is getting connection errors to Revit, or is running the plugin for the first time. Walks through installing the RevitMCP addin into Revit 2024 on Windows, enabling commands in the Revit ribbon, and verifying the MCP bridge is live.
---

# Setup Revit 2024 + Codex Bridge

This skill guides the user through the one-time setup required before any other skill in this plugin will work. The MCP server (`mcp-server-for-revit`) is only half of the bridge — the other half is a C# addin that runs inside Revit 2024 and listens for commands.

## Prerequisites Check

Before anything else, confirm the user has:

1. **Revit 2024** installed on Windows (check `C:\Program Files\Autodesk\Revit 2024\`)
2. **Node.js** installed (run `node --version` in PowerShell — any version 18+ is fine, `npx` is used to launch the MCP server)
3. **Codex** with this plugin enabled

If any are missing, stop and tell the user to install them first. Link to nodejs.org for Node.

## Step 1 — Install the Revit Addin

The MCP server talks to Revit through a C# addin that must live in Revit's addins folder.

1. Open a browser and go to the [releases page](https://github.com/mcp-servers-for-revit/mcp-servers-for-revit/releases).
2. Download the latest ZIP that matches **Revit 2024** (look for `RevitMCP-2024` or a "2024" suffix).
3. Extract the ZIP. You should see at least:
   - `RevitMCP.addin` — the manifest file
   - `RevitMCP.dll` + dependencies — the compiled plugin
   - A `Commands\RevitMCPCommandSet\2024\` folder with command DLLs
4. Copy **all extracted contents** into:

   ```
   %AppData%\Autodesk\Revit\Addins\2024\
   ```

   Paste `%AppData%\Autodesk\Revit\Addins\2024\` into the Windows Explorer address bar — it expands to `C:\Users\<you>\AppData\Roaming\Autodesk\Revit\Addins\2024\`. Create the `2024` folder if it doesn't exist.

5. The final layout inside that folder should look like:

   ```
   Addins\2024\
   ├── RevitMCP.addin
   ├── RevitMCP.dll
   ├── ...other dlls...
   └── Commands\
       └── RevitMCPCommandSet\
           └── 2024\
               └── ...command dlls...
   ```

## Step 2 — Enable the Addin in Revit

1. Launch **Revit 2024**.
2. If Windows shows a security warning about loading unsigned code, click **Always Load**. If you click "Do not load," the addin will not appear.
3. Once Revit is open, look for a new **RevitMCP** tab (or a panel on the **Add-Ins** tab — depends on the release).
4. Click **Settings** on that panel. In the settings dialog:
   - Toggle **Enable MCP Bridge** on.
   - Leave the default port (usually `8080`) unless the user has a reason to change it.
   - Click **Start Listening** (or equivalent).
5. Open a blank project or any existing `.rvt` file. The bridge only responds when a document is open.

## Step 3 — Verify the Connection from Claude

From the user's side in Codex:

1. Make sure the `revit-mcp-cowork` plugin is enabled.
2. Ask Claude: "Call the Revit `say_hello` tool."
3. If Claude gets a hello response, the bridge is working — continue.
4. If Claude gets a timeout or connection refused:
   - Confirm Revit is open with a document loaded.
   - Confirm the RevitMCP panel shows "Listening" status.
   - Check Windows Firewall isn't blocking `localhost:8080`.
   - Restart Revit and retry.

## Step 4 — Sanity Check

Once `say_hello` works, call `get_current_view_info`. This confirms the bridge can read live data from the open document. If this succeeds, setup is complete.

## What to Tell the User After Setup

Keep it short. Tell them:

- They can now ask in natural language — e.g., "create 5 levels 3m apart," "tag all walls in this view," "show me a material takeoff."
- Other skills in this plugin (`scaffold-project`, `quick-model`, `model-audit`, etc.) will automatically take over for their respective workflows.
- The Revit bridge must stay running in Revit for any skill to work. Closing Revit breaks the connection.

## Common Setup Issues

| Symptom | Likely cause | Fix |
|---|---|---|
| No RevitMCP tab after launch | Addin files in wrong folder | Verify path is `%AppData%\Autodesk\Revit\Addins\2024\`, not `ProgramData` |
| Revit shows "blocked" warning each launch | Unsigned addin | Right-click each DLL → Properties → Unblock, or accept "Always Load" on first launch |
| MCP server starts but `say_hello` times out | Bridge not started in Revit | Open Revit, click Settings on RevitMCP panel, click Start |
| Port conflict | Another app uses 8080 | Change port in Revit settings and update `.mcp.json` env to match |
| "Document is not active" errors | No file open in Revit | Open any `.rvt` document before calling tools |

## If the User Wants a Different Revit Version

This plugin targets Revit 2024. The server supports 2020–2026 if they swap the addin build — direct them to download the matching release and copy it into `Addins\<version>\`. No other changes needed on the Cowork side.

## Health check — run this at the start of every session

Before doing any significant work (scaffold, mirror, bulk mods, code-runner), verify the bridge is live. Two-step check, both non-blocking:

**Step 1 — connection ping (via `send_code_to_revit`, NOT `say_hello`)**

**Do not use `say_hello`.** The upstream `say_hello` handler shows a modal `TaskDialog` in Revit that halts the UI until a human dismisses it — catastrophic for automation.

Instead, call `send_code_to_revit` with this snippet:

```csharp
return new {
    ok = true,
    title = document?.Title ?? "(no document)",
    viewName = document?.ActiveView?.Name ?? "(no view)",
    viewType = document?.ActiveView?.ViewType.ToString() ?? "(none)",
    revitVersion = document?.Application?.VersionNumber ?? "(unknown)",
    levelCount = new FilteredElementCollector(document)
        .OfClass(typeof(Level))
        .GetElementCount()
};
```

Must return within ~5 seconds. If it times out or errors:
- Revit is closed → tell user to open it.
- Bridge is stopped → tell user to click Start in the RevitMCP panel.
- Port conflict → restart Revit.
- Revit is in a modal dialog → the user has to dismiss it.

**Step 2 — verify active document via `get_current_view_info`**

A second read-only check to confirm the bridge can produce data:
- If it returns "no active document," Revit is open but no `.rvt` is loaded. Tell the user to open a project file.
- If it returns an unexpected view (e.g., schedule or drafting), tell the user which view Claude will be working against — this affects every view-scoped tool (tags, colors, visibility).

Run this health check implicitly at the start of any long or destructive operation (scaffold, mirror, bulk delete, C# code push). A failed health check halts the operation before any side effect lands.

When the user's first message in a session mentions Revit, run the health check first even if no heavy op is planned. Report results in one line:

> ✔ Revit 2024 bridge live. Document: `ProjectX.rvt` | view: `Level 2 — Floor Plan` | 5 levels | build 2024.3.

On retry-worthy failure (generic 2-minute timeout on first call), **retry once**. If the retry also fails, stop and surface the fix steps from the troubleshooting table. Never silently retry more than once — repeated hangs indicate a real problem.
