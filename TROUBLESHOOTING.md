# Troubleshooting

Common problems with the `revit-mcp-cowork` plugin and how to fix them. Organized by surface — start with the section matching where the error appears.

## The Revit bridge

### "MCP server failed to start" / `npx` errors

Symptom: Codex logs show the MCP server exiting immediately, or tools aren't available.

Fixes:

- **Node not installed.** Install Node 18+ from [nodejs.org](https://nodejs.org). `node --version` should print something.
- **npx not on PATH.** Close and reopen Cowork after installing Node. Cowork only reads PATH at launch.
- **Corporate network blocks npm registry.** The first run of `npx -y mcp-server-for-revit` downloads the package. If npm is blocked, pre-install globally on a connected machine (`npm install -g mcp-server-for-revit`) and change `.mcp.json` to launch the global binary instead of `npx`.
- **Antivirus blocks `npx.cmd`.** Add an exception for `%AppData%\npm\` and the Node install directory.

### Tools are listed but `say_hello` times out

Symptom: Claude can see the Revit MCP tool list, but calls hang or time out.

Fixes in order:

1. **Revit isn't open.** Open Revit 2024.
2. **No `.rvt` loaded.** Open any project file. Tools don't respond without an active document.
3. **The Revit addin bridge is stopped.** On the Revit ribbon, find the RevitMCP panel, open Settings, click **Start Listening**.
4. **Port conflict.** Default is `8080`. If another app uses it, change the port in the Revit Settings dialog and restart. No Cowork-side config change needed — the server and addin auto-discover via localhost.
5. **Windows Firewall blocks localhost.** Unusual but possible on hardened machines. Add an exception for Revit.exe.
6. **The addin didn't load at Revit startup.** Revit shows a warning on first load — click **Always Load**. If you clicked **Do Not Load** once, uninstall and reinstall the addin (delete the files from `%AppData%\Autodesk\Revit\Addins\2024\` and redo the setup).

### RevitMCP tab missing from Revit ribbon

- Addin files are in the wrong folder. Path must be **exactly** `%AppData%\Autodesk\Revit\Addins\2024\` — not `ProgramData`, not `Program Files`, not `Documents`.
- The `.addin` manifest file is missing. The release ZIP should include `RevitMCP.addin` — without it, Revit ignores the DLLs.
- Revit loaded the addin but threw a .NET version mismatch. Check Revit's Journals folder (`%LocalAppData%\Autodesk\Revit\Autodesk Revit 2024\Journals\`) for errors referencing `RevitMCP`.

### Bridge works but operations fail mid-transaction

Symptom: Tools return "Attempt to modify document outside of a transaction" or similar API errors.

Likely cause: custom C# sent via `revit-code-runner` or `revit-mirror`'s push phase is missing the `using (var t = new Transaction(...))` wrapper. Re-review the generated code before re-running.

## The Excel mirror

### "Lock file present" / refusal to write

Symptom: The mirror aborts with a message about `~$doors.xlsx`.

Fix: somebody has the file open in Excel. Ask them to close it. If nobody actually has it open:

1. Check your Task Manager for orphan `EXCEL.EXE` processes. Kill them.
2. If the `~$` lock file itself is more than an hour old, it's probably orphaned from an Excel crash. Delete it manually in File Explorer and retry.

### "Mtime changed — re-read or overwrite?"

Meaning: somebody saved the file between Claude's read and Claude's write. Almost always a concurrent user on another machine.

Fix: choose re-read, not overwrite. Overwriting destroys whatever they just saved. If you're sure it's safe (you know what changed and it doesn't conflict), you can force the overwrite, but be explicit.

### The mirror wrote but the NAS copy didn't update

Symptom: Claude says "applied X changes to doors.xlsx" but the team's copy on QNAP looks unchanged.

Likely causes:

- **Not actually a mount.** You edited a local copy. Check the path Claude reported — if it doesn't start with the mounted drive letter or `/Volumes/...`, you worked on something local.
- **Mount dropped during write.** Re-run; the atomic-write pattern means the original file is untouched on failure. Remount and retry.
- **OS-level caching on the reading machine** — rare, but the machine viewing the NAS file may need a folder refresh. File Explorer F5, or close and reopen the file.

### "I edited the xlsx and Claude didn't see my changes"

Classic re-read problem. Claude is reasoning from the xlsx state at the start of the session. Tell Claude explicitly: "re-read doors.xlsx before applying" or just "pull fresh from the file first."

The `revit-mirror` skill's Guard 1 forces a fresh read on every run — but if you're in a pure Excel query session (no mirror), Claude won't auto-re-read.

## Plugin install / enable

### Skills don't fire on expected phrases

- Make sure the plugin is enabled in Cowork's plugins list.
- Each skill has a description listing the trigger phrases. If the phrase is unusual, invoke the skill explicitly by name.
- If a recently-updated version isn't loading, fully quit Cowork and relaunch — plugin manifests are cached at start.

### `.plugin` file won't install

- Ensure it's a zip with `.plugin` extension (not `.zip`). Renaming a `.zip` works.
- The top of the zip must contain `.codex-plugin/plugin.json`. If the zip wraps an extra folder level, Cowork can't find the manifest.

## Performance

### Mirror operations are slow

- **SMB over Wi-Fi is 10–50× slower than local disk.** For large sheets, mount over wired Ethernet if possible.
- **`anthropic-skills:xlsx` parses the whole workbook.** If the xlsx has >10k rows, consider splitting one tracker per category.
- **Revit queries for large models take time.** `analyze_model_statistics` on a 500MB RVT can take a minute. Claude is not hung.

### Revit becomes unresponsive

- Bulk pushes (>200 rows in one transaction) can lock Revit's UI. The `revit-excel-sync` push and `revit-mirror` both chunk internally; if you see unresponsiveness, the chunk size may be misconfigured for your model's complexity. Ask for smaller chunks: *"push in batches of 50."*

## Where to look for more info

- Upstream MCP server: [mcp-servers-for-revit](https://github.com/mcp-servers-for-revit/mcp-servers-for-revit) releases and issues.
- Revit journal logs: `%LocalAppData%\Autodesk\Revit\Autodesk Revit 2024\Journals\` — every API error Revit saw is in here.
- Cowork's own log: in Cowork, Help → View Logs.

If none of the above resolves the issue, open an issue on this plugin's repo with: the exact user prompt, the Claude response, any error text, and the contents of the most recent Revit journal file.
