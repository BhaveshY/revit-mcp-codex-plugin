---
name: revit-mirror
description: Use when a single user prompt asks for BOTH a Revit change AND an Excel update — e.g., "change all Level 2 doors to 1000mm and update doors.xlsx", "delete these walls and keep the schedule in sync", "add a room and mirror it to rooms.xlsx", or any prompt that names a `.xlsx` file alongside a Revit action. Also use when the user has pinned a tracker sheet and said to keep it current. Orchestrates the Revit operation first, then updates only the affected rows in the target workbook.
---

# Revit + Excel — Single-Prompt Mirror

Use this skill when the user wants **one prompt to change two systems**. This is the everyday workflow for BIM teams that maintain an Excel tracker alongside their model — they describe what to change, the model gets changed, the tracker stays current. No flipping between windows.

## When this skill applies

Trigger on any prompt that contains **both** of:

1. A Revit modification verb — "change," "add," "delete," "move," "renumber," "retype," "update," "tag," "place," "replace," "fix," etc.
2. An Excel destination — either an explicit `.xlsx` filename, or a reference to "the sheet," "the tracker," "the schedule," "the BOQ," "our Excel," etc.

Also trigger when the user has previously pinned a sheet (see **Pinned sheet** below) and issues any Revit modification. Absence of an explicit xlsx mention doesn't mean "don't mirror" — it means "use the pin."

Examples that should trigger this skill:

- "Change every door on Level 2 to type `Double-Flush 1000×2134` and update `doors.xlsx`"
- "Delete all generic models and keep the BOQ in sync"
- "Add a fire-rated partition between rooms 203 and 204 and log it in `walls-tracker.xlsx`"
- "Renumber rooms on Level 3 sequentially and mirror to the room schedule"
- After `pin doors.xlsx`: "Swap the three north-facade doors to sliding panels" → mirror triggers automatically

> **Critical**: apply every rule from the `revit-tool-safety` skill. Mirror-specific gotchas:
> - The Phase 1 "identify affected elements" step uses `ai_element_filter`. **Pass `maxElements: 100000`** — otherwise the affected-element set is silently capped at 50 and the Excel half will only update 50 rows even if Revit changed more.
> - The Phase 3 "re-query affected elements' current state" also needs `maxElements: 100000`.
> - For `delete` mirrors, `delete_element` cascades — snapshot model counts before/after and report cascades in the Excel sheet too (status column).
> - Capture `get_current_view_info` before Phase 2 and compare after — `tag_all_rooms`, `operate_element SelectionBox/SetColor` can silently switch views.

## The orchestration pattern

Run in **three phases**, in this order. Never interleave.

### Phase 1 — Plan

Before touching anything:

1. **Identify the Revit operation** and which existing skill owns it:
   - Placement / geometry creation → delegate to `quick-model` or `scaffold-project`
   - Bulk parameter change, filter-and-modify → delegate to `find-and-modify`
   - Tagging / dimensioning / room placement → delegate to `document-model`
   - Anything custom → delegate to `revit-code-runner`
2. **Identify the target xlsx**: explicit filename in the prompt, or the pinned sheet. Resolve to an absolute path.
3. **Identify the scope**: which elements will the change affect? Call `ai_element_filter` to get the list *before* the change so you know the exact rows to update afterward. Hold the set of `UniqueId`s in memory.
4. **State the plan** back to the user in two lines:
   > Going to: change 14 doors on Level 2 → type `Double-Flush 1000×2134`.
   > Then update rows D-201 through D-214 in `doors.xlsx` (mirror).
5. If the change is destructive (delete, bulk type swap, mass parameter overwrite), **ask for confirmation**. Non-destructive edits proceed.

### Phase 2 — Execute in Revit

Delegate to the owning skill and run the actual change. Collect the tool response — you need to know which elements changed and what their new parameter values are.

On failure: stop. Do not touch the xlsx. Tell the user what broke, suggest a fix, leave Excel untouched.

### Phase 3 — Mirror to Excel

Only on Phase 2 success:

1. **Re-query Revit** for the affected elements' current state — use the `UniqueId` set from Phase 1 plus `ai_element_filter`. Pull the same columns that the xlsx already has.
2. **Read the xlsx** via local XLSX handling to find the header row and identify which rows in the sheet correspond to the affected `UniqueId`s.
3. **Compute a cell-level diff**: for each changed element, which columns actually differ from what's currently in the sheet.
4. **Write back**:
   - For elements that exist in the sheet: update just the changed cells. Preserve formatting, formulas, other columns.
   - For newly-created elements: append as new rows at the bottom.
   - For elements that were deleted from Revit: mark the row (add a `Status` column set to `Deleted` rather than removing, unless the user said "remove from sheet").
5. **Save** and report both halves in one summary:

   ```
   ✔ Revit: 14 doors on Level 2 swapped to Double-Flush 1000×2134
   ✔ Excel (doors.xlsx):
       • 14 rows updated (Width: 900→1000 mm, Type: Single→Double-Flush)
       • 0 rows added
       • 0 rows marked deleted
   ```

## Pinned sheet

To make the one-prompt workflow stick without having to name the xlsx every time, the user can **pin** a file:

> "Pin `C:\Projects\ProjectX\trackers\doors.xlsx` as the doors tracker."

Save the pin to user memory as a reference-type entry: `revit_mirror_pin_doors → path`. Do the same per category the user cares about — doors, windows, walls, rooms, etc. The memory entries are per-category.

On subsequent prompts that match a category (e.g., any door modification), look up the pin and mirror automatically — the user doesn't have to mention the file.

To unpin:

> "Stop mirroring doors."

Remove the memory entry.

Pinning also persists the **key field** used in that xlsx (`UniqueId` vs `Mark`) and the column set, so the mirror always matches the sheet's existing structure.

## Guardrails

- **Revit first, always.** Never update the xlsx before the Revit change is confirmed successful. A failed Revit op with a successful Excel write leaves the sheet lying about the model state — worse than both failing.
- **Cell-level diff, not row-level rewrite.** If a user has a formula in column K and the mirror rewrites the whole row, formulas die. Only touch cells that changed.
- **Never add columns the user didn't authorize.** Mirror respects the sheet's schema. If Revit has a parameter the xlsx doesn't track, leave it out of the mirror.
- **Deleted elements don't vanish from the sheet by default.** Teams audit xlsx history — silent row deletion breaks that. Mark them `Deleted` and let the user prune when they want.
- **Destructive operations always confirm.** Bulk deletions, type swaps, mass renumbering — these all get a preview and a yes/no even when a pin is active.
- **Single mirror target per prompt.** If the user names two xlsx files, ask which one is the mirror and which is the source. Don't guess.
- **State the pin in use.** Every mirror report includes which sheet was updated and (if applicable) that a pin was used, so the user isn't surprised by an unseen file change.

## Freshness guards (required before every write)

The xlsx may live on a mounted NAS where other users or an open Excel session can mutate it between Codex's read and write. Apply these four guards on every mirror run. They are non-optional. See [references/safety-patterns.md](references/safety-patterns.md) for code templates.

### Guard 1 — Re-read fresh before every write

Never operate on xlsx data that Codex read in an earlier conversation turn. At the start of Phase 3 (Mirror), always re-read the file from disk. If the file content was loaded 10 turns ago, it's stale by definition.

### Guard 2 — Lock-file detection

Before any write, check the target directory for Excel's lock file:

- Windows / cross-platform: `~$<filename>.xlsx` in the same directory (hidden file).
- If present: someone has the xlsx open in Excel. Refuse the write. Tell the user who to nudge ("lock file present — close the file in Excel and retry") and stop.

Do not attempt to write over a locked file "hoping Excel will handle it." Excel's conflict dialog may surface on another machine, and the write will either silently fail or create a `Copy of` file the user won't see.

### Guard 3 — Mtime / ETag check

Record the file's last-modified timestamp at the start of Phase 3 read. Re-stat right before write. If the timestamp changed, somebody saved the file in between — abort and warn:

> The sheet was modified (by user or app) 43 seconds ago. Re-read and retry, or overwrite anyway?

Default to aborting. Only overwrite on explicit user yes. This is the single most important guard — it catches the real-world case where a colleague saves from another workstation between your read and your write.

### Guard 4 — Atomic write pattern

Never write directly to the destination path. Instead:

1. Write the new bytes to `<filename>.xlsx.tmp.<pid>` in the same directory.
2. Flush and close.
3. Rename `<filename>.xlsx.tmp.<pid>` → `<filename>.xlsx`. On SMB and NTFS this is atomic for same-directory renames.

Result: a network drop, a process crash, or a disk full error leaves the original file untouched. Either the whole write succeeded, or nothing changed.

### Backup-on-bulk

For any mirror that will write to more than 50 rows or touch more than 3 categories in one run, create a timestamped backup **before** the atomic write:

```
<filename>.backup.<YYYY-MM-DDTHH-MM-SS>.xlsx
```

Keep it in the same directory unless a `backups/` subdirectory exists (use that if so). Report the backup path to the user. They can prune later.

### Reporting after all guards pass

The final summary must state:

- The four guards ran and passed (or which one halted the mirror and why).
- The backup file path, if one was created.
- The Revit operation result.
- The cell-level diff applied to the xlsx.

If any guard fails, Revit was already changed by Phase 2. Tell the user the xlsx mirror did not complete and give them two options: fix the xlsx condition (close Excel / pull fresh) and retry just the mirror half, or roll back Revit manually via Ctrl-Z.

## Inverse — Excel-first mirror

If the user's prompt starts in Excel ("I changed widths in the sheet, apply everything"), this is the `revit-excel-sync` PUSH workflow — hand off to that skill directly. `revit-mirror` is for Revit-first prompts specifically.

## Example conversations

> **User**: "Change all doors on Level 2 to 1000mm wide and keep `doors.xlsx` in sync"
>
> **You (plan)**: "Going to change 14 doors → 1000mm, then update 14 rows in doors.xlsx."
> **You (execute)**: calls `find-and-modify` to filter doors on Level 2, uses `send_code_to_revit` to set width per type (warn about type parameter ripple if needed).
> **You (mirror)**: reads doors.xlsx, finds the 14 rows, updates Width column only.
> **You (report)**: both halves in one summary.

> **User (after pinning doors.xlsx)**: "Delete door D-205"
>
> **You (plan)**: "Going to delete D-205 (UniqueId abc…). Will mark its row Deleted in doors.xlsx (pinned)."
> **You (confirm delete)**: "Delete 1 door? Y/N"
> **You (execute)**: `delete_element`.
> **You (mirror)**: finds D-205 row, sets Status=Deleted.
> **You (report)**: done.

> **User**: "Add 4 rooms on the north wing and log them"
>
> **You**: places 4 rooms via `document-model`, assigns numbers, then appends 4 rows to the pinned rooms.xlsx.

## If no pin exists and no xlsx is in the prompt

Ask which sheet to mirror to, or offer to create a new one. Don't silently do the Revit half without the mirror — that's the opposite of what this skill is for.

## If the xlsx lives on a NAS / network share (QNAP, Synology, SMB server)

This is the common office setup. The plugin can't reach a NAS unless the share is either mounted as a local drive on the Codex host or exposed through an MCP bridge. Before the first mirror run on a NAS-hosted tracker:

1. Verify the file opens at a local path (e.g., `Z:\Projects\doors.xlsx` on Windows after mapping, or `/Volumes/Projects/doors.xlsx` on Mac).
2. If it doesn't, read [references/network-storage.md](references/network-storage.md) — it covers the three practical patterns: mount as drive, local staging copy, or File Station HTTP API.
3. If the user says "the sheet is on our QNAP" and gives a UNC path like `\\qnap.local\...`, do **not** attempt to access it directly. Walk through mounting first.
4. Once mounted/accessible, pin the file with its mounted path and proceed normally.

Do not silently fall back to creating a local-only copy of a NAS file — the team will lose track of which copy is canonical.
