---
name: setup-revit
description: Use when the user asks to "set up Revit", "install the Revit plugin", "connect Revit to Codex", "configure the Revit MCP", is getting connection errors to Revit, or is running the plugin for the first time. Walks through installing the Revit MCP addin into Revit 2024 on Windows, enabling the Revit bridge, and verifying the MCP connection from Codex Desktop.
---

# Setup Revit 2024 + Codex Bridge

This skill guides the user through the one-time setup required before any other Revit skill will work. The MCP server (`mcp-server-for-revit`) is only half of the bridge; the other half is a C# addin that runs inside Revit 2024 and listens for commands.

## Prerequisites Check

Before anything else, confirm the user has:

1. Revit 2024 installed on Windows. Check `C:\Program Files\Autodesk\Revit 2024\`.
2. Node.js 22 LTS installed or available at `%USERPROFILE%\.local\nodejs22`. Node 20+ is supported, but Node 22 is the tested path for the MCP server native dependency.
3. Codex Desktop with this plugin installed and enabled.

If any are missing, stop and tell the user to install them first. For a fresh Windows setup from this repo, recommend:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows-codex-desktop.ps1
```

## Step 1: Install The Revit Addin

The MCP server talks to Revit through a C# addin that must live in Revit's addins folder.

1. Open the upstream release page: `https://github.com/mcp-servers-for-revit/mcp-servers-for-revit/releases/tag/v1.0.0`.
2. Download `mcp-servers-for-revit-v1.0.0-Revit2024.zip`.
3. Extract the ZIP. It should contain one or more `.addin` manifest files and the Revit MCP addin payload folder.
4. Copy all extracted addin contents into:

   ```text
   %AppData%\Autodesk\Revit\Addins\2024\
   ```

   Paste that path into Windows Explorer. It expands to `C:\Users\<you>\AppData\Roaming\Autodesk\Revit\Addins\2024\`. Create the `2024` folder if it does not exist.

## Step 2: Enable The Addin In Revit

1. Launch Revit 2024.
2. If Revit warns about loading unsigned code, choose `Always Load`. If the user chooses `Do Not Load`, the addin will not appear.
3. Open a blank project or any existing `.rvt` file. The bridge only responds when a document is open.
4. Find the Revit MCP panel, open Settings if needed, and click `Start Listening`.
5. Leave the default port, usually `8080`, unless the user has a specific reason to change it.

## Step 3: Verify The Connection From Codex

From the user's side in Codex:

1. Fully quit and reopen Codex Desktop after installing the plugin, changing PATH, or installing Node.
2. Make sure the `revit-mcp-cowork` plugin is enabled.
3. Do not call `say_hello`; it opens a blocking modal dialog inside Revit.
4. Ask Codex: `Run a Revit health check.`
5. If Codex gets a timeout or connection refused:
   - Confirm Revit is open with a document loaded.
   - Confirm the Revit MCP panel shows listening/running status.
   - Confirm Node is available with `node --version`.
   - Confirm the npm bridge is installed with `npm list -g mcp-server-for-revit`.
   - Restart Revit and retry once.

## Step 4: Sanity Check

After the non-blocking `send_code_to_revit` health check works, call `get_current_view_info`. This confirms the bridge can read live data from the open document. If this succeeds, setup is complete.

## What To Tell The User After Setup

Keep it short. Tell them:

- They can now ask in natural language, for example: "create 5 levels 3m apart", "tag all walls in this view", or "show me a material takeoff".
- Other skills in this plugin (`scaffold-project`, `quick-model`, `model-audit`, and others) will automatically take over for their respective workflows.
- The Revit bridge must stay running in Revit for any skill to work. Closing Revit breaks the connection.

## Common Setup Issues

| Symptom | Likely cause | Fix |
|---|---|---|
| No Revit MCP tab after launch | Addin files in wrong folder | Verify path is `%AppData%\Autodesk\Revit\Addins\2024\`, not `ProgramData` |
| Revit shows a blocked or unsigned warning | Unsigned addin | Choose `Always Load` on first launch |
| MCP server times out or refuses connections | Bridge not started in Revit | Open Revit, open a project, start the listener |
| Node install fails on `better-sqlite3` | Node 24 native build path | Install Node 22 LTS, then rerun `npm install -g mcp-server-for-revit` |
| "Document is not active" errors | No file open in Revit | Open any `.rvt` document before calling tools |

## If The User Wants A Different Revit Version

This plugin targets Revit 2024. The server supports 2020-2026 if the user installs the matching Revit addin build into `Addins\<version>\`. No other Codex-side config change is normally needed.

## Health Check: Run This At The Start Of Every Session

Before doing significant work, verify the bridge is live. Use this two-step check, both non-blocking.

### Step 1: connection ping via `send_code_to_revit`

Do not use `say_hello`. The upstream `say_hello` handler shows a modal `TaskDialog` in Revit and can halt automation until a human dismisses it.

Instead, call `send_code_to_revit` with this snippet:

```csharp
return new {
    ok = true,
    title = doc?.Title ?? "(no document)",
    viewName = doc?.ActiveView?.Name ?? "(no view)",
    viewType = doc?.ActiveView?.ViewType.ToString() ?? "(none)",
    revitVersion = doc?.Application?.VersionNumber ?? "(unknown)",
    levelCount = new FilteredElementCollector(doc)
        .OfClass(typeof(Level))
        .GetElementCount()
};
```

It should return within about 5 seconds. If it times out or errors:

- Revit is closed: tell the user to open it.
- The bridge is stopped: tell the user to click Start in the Revit MCP panel.
- Revit has no document open: tell the user to open a project file.
- Revit is in a modal dialog: the user has to dismiss it.

### Step 2: verify active document via `get_current_view_info`

Use `get_current_view_info` as a second read-only check:

- If it returns no active document, Revit is open but no `.rvt` is loaded.
- If it returns an unexpected view, tell the user which view Codex will work against because this affects view-scoped tools.

Run this health check at the start of any long or destructive operation. A failed health check halts the operation before any side effect lands.

When the user's first message in a session mentions Revit, run the health check first even if no heavy operation is planned. Report results in one line:

```text
Revit 2024 bridge live. Document: ProjectX.rvt | view: Level 2 - Floor Plan | 5 levels | build 2024.3.
```

On retry-worthy failure, such as a generic first-call timeout, retry once. If the retry also fails, stop and surface the fix steps from the troubleshooting table.
