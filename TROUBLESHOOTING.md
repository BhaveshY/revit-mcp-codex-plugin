# Troubleshooting

Common problems with the `revit-mcp-cowork` plugin and how to fix them. Start with the section matching where the error appears.

## The Revit Bridge

### "MCP server failed to start" or `npx` errors

Symptom: Codex logs show the MCP server exiting immediately, or tools are not available.

Fixes:

- **Node not installed.** Install Node 22 LTS from [nodejs.org](https://nodejs.org). `node --version` should print `v22` or newer. Node 20+ is supported, but Node 22 is the tested path.
- **Node 24 native dependency install failed.** If `npm install -g mcp-server-for-revit` fails while building `better-sqlite3` or asks for Visual Studio C++ Build Tools, install Node 22 LTS and rerun `npm install -g mcp-server-for-revit`.
- **The npm bridge is not installed globally.** Run `npm install -g mcp-server-for-revit`. The plugin launcher prefers the global `mcp-server-for-revit.cmd` and only falls back to `npx -y mcp-server-for-revit`.
- **npx not on PATH.** Close and reopen Codex after installing Node. Codex only reads PATH at launch.
- **Corporate network blocks npm registry.** The first run of `npx -y mcp-server-for-revit` downloads the package. If npm is blocked, pre-install globally on a connected machine with `npm install -g mcp-server-for-revit`.
- **Antivirus blocks `npx.cmd`.** Add an exception for `%AppData%\npm\` and the Node install directory.

### Tools are listed but `say_hello` times out

Symptom: Codex can see the Revit MCP tool list, but calls hang or time out.

Fixes in order:

1. **Revit is not open.** Open Revit 2024.
2. **No `.rvt` is loaded.** Open any project file. Tools do not respond without an active document.
3. **The Revit addin bridge is stopped.** On the Revit ribbon, find the RevitMCP panel, open Settings, and click **Start Listening**.
4. **Port conflict.** Default is `8080`. If another app uses it, change the port in the Revit Settings dialog and restart. No Codex-side config change is needed because the server and addin auto-discover via localhost.
5. **Windows Firewall blocks localhost.** Unusual but possible on hardened machines. Add an exception for `Revit.exe`.
6. **The addin did not load at Revit startup.** Revit shows a warning on first load. Click **Always Load**. If you clicked **Do Not Load** once, uninstall and reinstall the addin by deleting the files from `%AppData%\Autodesk\Revit\Addins\2024\` and redoing setup.

### RevitMCP tab missing from Revit ribbon

- Addin files are in the wrong folder. Path must be exactly `%AppData%\Autodesk\Revit\Addins\2024\`, not `ProgramData`, not `Program Files`, and not `Documents`.
- The `.addin` manifest file is missing. The release ZIP should include `RevitMCP.addin`; without it, Revit ignores the DLLs.
- Revit loaded the addin but threw a .NET version mismatch. Check Revit's Journals folder at `%LocalAppData%\Autodesk\Revit\Autodesk Revit 2024\Journals\` for errors referencing `RevitMCP`.

### Bridge works but operations fail mid-transaction

Symptom: Tools return "Attempt to modify document outside of a transaction" or similar API errors.

Likely cause: custom C# sent via `revit-code-runner` or `revit-mirror` push phase is missing a `using (var t = new Transaction(...))` wrapper. Re-review the generated code before re-running.

## The Excel Mirror

### "Lock file present" or refusal to write

Symptom: The mirror aborts with a message about `~$doors.xlsx`.

Fix: somebody has the file open in Excel. Ask them to close it. If nobody actually has it open:

1. Check Task Manager for orphan `EXCEL.EXE` processes. Kill them.
2. If the `~$` lock file itself is more than an hour old, it is probably orphaned from an Excel crash. Delete it manually in File Explorer and retry.

### "Mtime changed - re-read or overwrite?"

Meaning: somebody saved the file between Codex's read and Codex's write. Almost always a concurrent user on another machine.

Fix: choose re-read, not overwrite. Overwriting destroys whatever they just saved. If you are sure it is safe, you can force the overwrite, but be explicit.

### The mirror wrote but the NAS copy did not update

Symptom: Codex says "applied X changes to doors.xlsx" but the team's copy on QNAP looks unchanged.

Likely causes:

- **Not actually a mount.** You edited a local copy. Check the path Codex reported. If it does not start with the mounted drive letter or `/Volumes/...`, you worked on something local.
- **Mount dropped during write.** Re-run. The atomic-write pattern means the original file is untouched on failure. Remount and retry.
- **OS-level caching on the reading machine.** Rare, but the machine viewing the NAS file may need a folder refresh. Use File Explorer F5, or close and reopen the file.

### "I edited the xlsx and Codex did not see my changes"

Classic re-read problem. Codex is reasoning from the xlsx state at the start of the session. Tell Codex explicitly: "re-read doors.xlsx before applying" or "pull fresh from the file first."

The `revit-mirror` skill's Guard 1 forces a fresh read on every run, but if you are in a pure Excel query session with no mirror, Codex will not auto-re-read.

## Plugin Install And Enable

### Skills do not fire on expected phrases

- Make sure the plugin is enabled in Codex's plugins list.
- Each skill has a description listing the trigger phrases. If the phrase is unusual, invoke the skill explicitly by name.
- If a recently updated version is not loading, fully quit Codex and relaunch; plugin manifests are cached at start.

### Marketplace install fails

- Use current Codex CLI commands:

  ```text
  codex plugin marketplace add https://github.com/BhaveshY/revit-mcp-codex-plugin
  codex plugin add revit-mcp-cowork@revit-mcp-codex-plugin
  ```

- The owner/repo form is also valid: `codex plugin marketplace add BhaveshY/revit-mcp-codex-plugin`.
- If installing from a ZIP, the top of the ZIP must contain `.codex-plugin/plugin.json`. If the ZIP wraps an extra folder level, Codex cannot find the manifest.

### Fresh Windows PC setup

If you want one command to prepare the Windows side after cloning the repo, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows-codex-desktop.ps1
```

This installs user-local Node 22 if needed, installs the npm bridge, downloads the Revit 2024 addin, and installs the Codex plugin from the GitHub repo source.

## Performance

### Mirror operations are slow

- **SMB over Wi-Fi is 10-50x slower than local disk.** For large sheets, mount over wired Ethernet if possible.
- **XLSX parsing reads the whole workbook.** If the xlsx has more than 10k rows, consider splitting one tracker per category.
- **Revit queries for large models take time.** `analyze_model_statistics` on a 500 MB RVT can take a minute. Codex is not hung.

### Revit becomes unresponsive

- Bulk pushes of more than 200 rows in one transaction can lock Revit's UI. The `revit-excel-sync` push and `revit-mirror` both chunk internally; if you see unresponsiveness, the chunk size may be misconfigured for your model's complexity. Ask for smaller chunks: "push in batches of 50."

## Where To Look For More Info

- Upstream MCP server: [mcp-servers-for-revit](https://github.com/mcp-servers-for-revit/mcp-servers-for-revit) releases and issues.
- Revit journal logs: `%LocalAppData%\Autodesk\Revit\Autodesk Revit 2024\Journals\`. Every API error Revit saw is in here.
- Codex logs or app diagnostics, depending on whether you are using the CLI or desktop app.

If none of the above resolves the issue, open an issue on this plugin repo with the exact user prompt, the Codex response, any error text, and the contents of the most recent Revit journal file.
