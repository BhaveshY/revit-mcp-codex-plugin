# Install the enterprise-accuracy fork

This file is written for an AI agent (Codex or Codex) to execute end-to-end. Every step has a concrete command and a concrete verification. A human can also read it and run the commands manually.

**Goal**: replace the upstream `mcp-servers-for-revit` C# addin with the fixed fork (`BhaveshY/mcp-servers-for-revit@v1.0.0-enterprise.1`) so that the main correctness bugs are fixed at the source. The C# addin changes fix six issues directly: count-after-Take, blocking modals, Chinese user-facing errors, cascade-deletion opacity, silent view switches, and deletion/reporting clarity. The TS default-limit issue can also be fixed at the source by doing the optional server swap in step 9.

**Platform**: Revit 2024 on **Windows**. The Revit API is Windows-only. Agents running on macOS / Linux should execute the Windows-side steps via SSH, RDP, or by asking the human to run them.

**Agent contract**:
- Read each step in order.
- Run the command under **Agent does**.
- Check the condition under **Verify**. If it fails, do not proceed — surface the error to the human and stop.
- Mark progress in your todo list as you go.

---

## 0. Prerequisites

The agent must confirm all three before starting:

| Requirement | Check command (PowerShell) | Expected |
|---|---|---|
| Revit 2024 installed | `Test-Path "C:\Program Files\Autodesk\Revit 2024\Revit.exe"` | `True` |
| `gh` CLI authenticated | `gh auth status` | `Logged in to github.com` |
| Node.js 18+ (for the plugin side) | `node --version` | `v18.x` or higher |

If any fail, stop and report which.

---

## 1. Enable Actions on the fork (one-time)

GitHub disables workflows on forks by default. Without this step, the CI never runs and no addin zip is produced.

**Agent does** — attempt to enable via API first; if that fails, instruct the human:

```bash
# Try API enable (may be enough if you've already visited the Actions tab once).
gh api -X PUT repos/BhaveshY/mcp-servers-for-revit/actions/permissions \
  -f enabled=true \
  -f allowed_actions=all

# Sanity check:
gh api repos/BhaveshY/mcp-servers-for-revit/actions/workflows \
  --jq '.total_count'
```

**Verify**: `.total_count` must be >= 1. If it's still `0`, the fork needs a **manual UI click**:

> Open [github.com/BhaveshY/mcp-servers-for-revit/actions](https://github.com/BhaveshY/mcp-servers-for-revit/actions) in a browser, then click **"I understand my workflows, go ahead and enable them"**.

After the human clicks, re-run the verify command. Do not proceed until `.total_count >= 1`.

---

## 2. Trigger the CI build

The tag `v1.0.0-enterprise.1` is already pushed. If Actions were just enabled, the tag push did NOT trigger a run, so retrigger it manually.

**Agent does**:

```bash
# Delete and re-push the tag to trigger the Release workflow.
cd /tmp/revit-mcp-fork
git push origin --delete v1.0.0-enterprise.1 2>/dev/null
git push origin refs/tags/v1.0.0-enterprise.1

# Alternative: workflow_dispatch if the yaml supports it
# (current release.yml does NOT, so the tag re-push is the right path).
```

**Verify**:

```bash
# Wait up to 60 seconds for the run to appear.
for i in 1 2 3 4 5 6; do
  RUN=$(gh run list --repo BhaveshY/mcp-servers-for-revit --limit 1 --json databaseId,status,conclusion --jq '.[0]')
  echo "Attempt $i: $RUN"
  if [ -n "$RUN" ] && [ "$RUN" != "null" ]; then break; fi
  sleep 10
done
```

You should see `status: queued` or `in_progress`. If after 60s nothing shows, Actions are still disabled — go back to step 1.

---

## 3. Wait for the build + release to finish

The Windows build is slow: about 8-15 minutes for all seven Revit versions (2020-2026).

**Agent does** — poll, but do not spam:

```bash
# Block until the latest run finishes. Checks every 30s.
gh run watch $(gh run list --repo BhaveshY/mcp-servers-for-revit --limit 1 --json databaseId --jq '.[0].databaseId') \
  --repo BhaveshY/mcp-servers-for-revit \
  --exit-status
```

**Verify** — the `build` job must be `success`:

```bash
gh run list --repo BhaveshY/mcp-servers-for-revit --limit 1 \
  --json conclusion,displayTitle --jq '.[0]'
```

Expected: `"conclusion": "success"`.

**Note**: the `npm-publish` job is expected to fail because the `mcp-server-for-revit` name on npm is owned by upstream. That failure does NOT block the release — the addin zips are attached inside the `build` job. Ignore the `npm-publish` red cross.

---

## 4. Download the Revit 2024 addin zip

**Agent does**:

```powershell
# PowerShell on the Windows machine where Revit is installed.
$tag    = "v1.0.0-enterprise.1"
$target = "$env:USERPROFILE\Downloads\revit-mcp-fork-$tag"
New-Item -ItemType Directory -Force -Path $target | Out-Null

gh release download $tag `
  --repo BhaveshY/mcp-servers-for-revit `
  --pattern "*Revit2024.zip" `
  --dir $target
```

**Verify**:

```powershell
Test-Path "$target\mcp-servers-for-revit-$tag-Revit2024.zip"
# Must print True
```

---

## 5. Back up the existing upstream addin (if present)

Never overwrite without a rollback path.

**Agent does**:

```powershell
$addinDir = "$env:AppData\Autodesk\Revit\Addins\2024"
$backupDir = "$env:AppData\Autodesk\Revit\Addins\2024.upstream-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

if (Test-Path $addinDir) {
  Copy-Item -Path $addinDir -Destination $backupDir -Recurse
  Write-Host "Backed up existing addin folder to: $backupDir"
}
```

**Verify**: `Test-Path $backupDir` prints `True` if there was an existing addin. Otherwise the folder is being freshly created in the next step.

---

## 6. Close Revit

Revit loads addins on startup and locks the DLLs while running. Installing over a live process corrupts the deployment.

**Agent does**:

```powershell
# Stop any running Revit process. Warn the user first.
Get-Process Revit -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host "WARNING: Revit is running (PID $($_.Id)). Save your work first."
}
# After confirmation:
Get-Process Revit -ErrorAction SilentlyContinue | Stop-Process -Force
```

**Verify**: `Get-Process Revit -ErrorAction SilentlyContinue` returns nothing.

---

## 7. Extract the fork's addin into the Revit addin folder

**Agent does**:

```powershell
$zip = "$target\mcp-servers-for-revit-$tag-Revit2024.zip"
$addinDir = "$env:AppData\Autodesk\Revit\Addins\2024"
New-Item -ItemType Directory -Force -Path $addinDir | Out-Null

# Remove any old upstream RevitMCP files first (they have the same names).
Remove-Item "$addinDir\RevitMCP*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$addinDir\revit-mcp*" -Recurse -Force -ErrorAction SilentlyContinue

# Extract the fork's build.
Expand-Archive -Path $zip -DestinationPath $addinDir -Force
```

**Verify** — the addin manifest must land in the right place:

```powershell
Get-ChildItem "$addinDir" -Filter "*.addin" | Select-Object -ExpandProperty Name
# Expect at least one .addin file referencing the RevitMCP DLL.
```

Also verify the DLL is present:

```powershell
Get-ChildItem "$addinDir" -Recurse -Filter "RevitMCP*.dll" | Select-Object FullName
```

---

## 8. Start Revit and confirm the addin loads

**Agent does** — prompt the human:

> Launch **Revit 2024** and open any project file. After the ribbon loads, look for the **RevitMCP** tab or button. If the tab is missing, the DLL did not load correctly.

**Verify via the MCP bridge** (from Codex, with this plugin installed):

Ask Codex: *"Run a Revit health check."*

The `setup-revit` skill should fire a non-blocking `send_code_to_revit` ping. Expected response: the ping returns within a few seconds with a document-info dump. Old upstream addin would hang on `say_hello`'s blocking modal; the fork fixes that.

---

## 9. Optional — switch the plugin's TS server to the fork's build

The C# addin fixes cover the Revit-side correctness issues. The TS default-limit issue is separate: if you also want the MCP server itself to stop defaulting to small list caps, swap the plugin over to the fork's TS build.

### 9a. Easy path — keep the hooks

Do nothing. The plugin's `PreToolUse` hook continues to block unsafe-limit calls on the four list tools, so silent truncation is already prevented client-side. This is the recommended default unless you specifically want the forked TS server too.

### 9b. Use the fork's TS server instead of upstream

The fork's TS server is in the same repo as the C# addin (`server/` directory). To use it:

```powershell
cd $env:USERPROFILE
git clone --branch v1.0.0-enterprise.1 https://github.com/BhaveshY/mcp-servers-for-revit.git revit-mcp-fork-local
cd revit-mcp-fork-local\server
npm ci
npm run build
```

Then edit the plugin's `.mcp.json` to point at the local build instead of `npx -y mcp-server-for-revit`:

```json
{
  "mcpServers": {
    "revit": {
      "command": "node",
      "args": ["C:/Users/<you>/revit-mcp-fork-local/server/build/index.js"]
    }
  }
}
```

Restart Codex for the change to pick up.

**Verify**: in Codex, ask it to list doors with no explicit limit. Response should include up to the real door count, not be capped at 50 or 100.

---

## 10. Verify the fixes landed

Run this checklist via Codex:

| Check | Ask Codex | Pass condition |
|---|---|---|
| Count accuracy | "How many doors are in this project?" | Returns the real count with the source tool cited (`analyze_model_statistics` or `send_code_to_revit`), not a round-capped 50 or 100. |
| English errors | "Run `ai_element_filter` on an invalid category name like `OST_Nonsense`." | Error message is in English, e.g. `"Cannot convert 'OST_Nonsense' to a valid Revit BuiltInCategory."` No Chinese characters. |
| Cascade deletion | "Delete wall ID X" (pick a wall hosting doors) | Response shows `directDeletedCount`, `cascadeDeletedCount`, and `totalDeletedCount` as separate fields. |
| View-switch report | "Isolate elements X, Y, Z using SelectionBox from a plan view" | Result message includes `"view switched from 'Plan X' to '{3D}'"` if a switch was forced. |
| Non-blocking health | "Run the Revit health check." | Returns within about 2 seconds. Revit UI stays responsive, with no modal to dismiss. |

If any check fails, roll back (step 11) and surface which one.

---

## 11. Rollback

If anything goes wrong, restore the upstream addin in two steps:

```powershell
# 1. Close Revit.
Get-Process Revit -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. Restore the backed-up addin folder from step 5.
$latestBackup = Get-ChildItem "$env:AppData\Autodesk\Revit\Addins\" -Directory `
  | Where-Object { $_.Name -match "2024\.upstream-backup-" } `
  | Sort-Object LastWriteTime -Descending `
  | Select-Object -First 1

$addinDir = "$env:AppData\Autodesk\Revit\Addins\2024"
Remove-Item $addinDir -Recurse -Force
Copy-Item $latestBackup.FullName $addinDir -Recurse

Write-Host "Rolled back to upstream addin: $($latestBackup.Name)"
```

Then reopen Revit. The upstream behavior is back.

---

## Fast path

1. Enable Actions at [github.com/BhaveshY/mcp-servers-for-revit/actions](https://github.com/BhaveshY/mcp-servers-for-revit/actions).
2. Re-push the tag: `git push origin --delete v1.0.0-enterprise.1 && git push origin refs/tags/v1.0.0-enterprise.1`.
3. Wait about 15 minutes for CI.
4. Run `gh release download v1.0.0-enterprise.1 --repo BhaveshY/mcp-servers-for-revit --pattern "*Revit2024.zip"`.
5. Close Revit and extract the zip into `%AppData%\Autodesk\Revit\Addins\2024\`.
6. Start Revit and confirm the RevitMCP ribbon is there.
7. In Codex, run the Revit health check.

Total time is about 20 minutes, most of it waiting for CI.

---

## Known caveats

- **`npm-publish` CI job fails.** Expected — the `mcp-server-for-revit` npm package name is owned by upstream. The `build` job still succeeds and produces the addin zips; ignore the `npm-publish` failure. If you want your own published package later, rename `server/package.json` to something like `@bhaveshy/mcp-server-for-revit` and add an `NPM_TOKEN` secret to the fork.
- **Revit 2025 and 2026 compatibility is not tested.** The addin is built for all seven Revit versions by CI, but only 2024 has been targeted here.
- **The family-substitution warning is still pending.** The fork improves the major enterprise bugs, but `create_*` tools can still succeed with a nearby family type without loudly telling the agent. Treat that as a follow-up improvement, not something already solved by this install.
- **Upstream drift.** When upstream adds features, rebase `fix/enterprise-accuracy` onto `upstream/main` and push a new tag like `v1.0.0-enterprise.N`.
