---
name: revit-excel-sync
description: Use when the user asks to "sync Revit with Excel", "update Excel from Revit", "update Revit from Excel", "export doors to Excel", "push spreadsheet changes to Revit", "round-trip my BOQ", "keep the schedule in sync", or mentions an Excel sheet alongside a Revit model. Runs bidirectional sync between a `.xlsx` workbook and a Revit 2024 document — pull elements to Excel, push edits back to Revit, or diff both sides.
---

# Revit ⇄ Excel Sync

Use this skill whenever Revit data and an Excel workbook must stay aligned — typical case: the team maintains door/window/room schedules in Excel while the geometry lives in Revit, and both sides drift apart.

This skill **orchestrates**; it handles workbook file I/O with whatever XLSX-capable workflow is available in the Codex environment, and Revit reads use the standard MCP tools. Writes back to Revit use the `send_code_to_revit` tool (with the show → confirm → run discipline from `revit-code-runner`).

## When this skill applies

- "The Excel sheet has the latest door sizes — update Revit."
- "Export rooms to our project schedule.xlsx."
- "What's different between this workbook and the model right now?"
- "Pull every wall's type and fire rating into a spreadsheet."
- "I changed marks in Excel — push them back."
- "Keep the BOQ spreadsheet in sync."

## Three modes

Pick one at the start and tell the user which:

| Mode | Direction | Destructive? |
|---|---|---|
| **Pull** (`revit → excel`) | Writes xlsx from live Revit data | No (only touches the xlsx file) |
| **Push** (`excel → revit`) | Updates Revit parameters from xlsx rows | **Yes** — changes the model |
| **Diff** (compare only) | Reports differences, no changes | No |

If the user said "sync," ask (or infer from context) which direction. "Update Excel" → pull. "Update Revit" → push. "Check" / "compare" → diff.

> **Critical**: apply every rule from the `revit-tool-safety` skill. Sync-specific gotchas:
> - `ai_element_filter` defaults to 50 elements — **always pass `maxElements: 100000`** or the pull will silently miss rows.
> - `get_available_family_types` caps at 100 with no total field — always pass `limit: 100000`.
> - `export_room_data` returns Area/Volume in **ft²/ft³** — convert before writing to the xlsx (usually the sheet expects m²/m³ or mm).
> - Before writing a PUSH, cross-verify the expected update count via `analyze_model_statistics` or a `send_code_to_revit` count to make sure the filter matched what the user meant.

## Required tools

**From Revit MCP**
- `ai_element_filter` — find elements by category & parameters. **Always** pass `maxElements: 100000`.
- `get_available_family_types` — pass `limit: 100000` when listing type options for push.
- `export_room_data` — fast path for rooms. Convert ft²/ft³ to mm or m² before writing.
- `analyze_model_statistics` — cross-verify expected vs actual counts before a push commits.
- `send_code_to_revit` — the only way to **write parameters** back to Revit, and the way to get unit-consistent reads beyond the standard tool units.
- `get_current_view_info` — scope confirmation.

**From local XLSX handling**
- Read workbook, identify sheet + header row
- Write workbook with preserved formatting
- Diff two tabular datasets

Do not invoke `anthropic-skills:xlsx`; it is Claude-specific and may not exist in Codex. Prefer an installed XLSX skill if one is present, or Python with `openpyxl` if it is already available. If no XLSX writer is available, ask before installing a dependency or offer CSV instead.

## The key field problem — solve it first

Every sync needs a stable identifier per element. Three options, in preference order:

1. **`UniqueId`** — Revit's permanent GUID. Never reused, survives rename/retyping. Best for machine-generated sheets.
2. **`Mark`** — the human-readable instance parameter most teams already use (`D-101`, `W-23`). Best when the team maintains the sheet manually.
3. **`Id`** — the integer ElementId. Fast but **not portable across sessions if elements are recreated**. Use only for in-session ops.

Ask the user which key to use. If the xlsx already exists, inspect the columns and auto-pick the first of `UniqueId` → `Mark` → `Id` that's present. State your choice.

A sheet without any of these is unreliable. Refuse to push from such a sheet — say so and offer to pull first, which will include `UniqueId` as a hidden column.

## Workflow: PULL (Revit → Excel)

1. **Scope the pull.** What category? Doors, windows, walls, rooms, all? If the user said "elements," ask or assume the top-level categories (walls, doors, windows, rooms, floors).
2. **Pick columns.** Default column set per category (see `references/parameter-mappings.md`). User can override.
3. **Query Revit.** `ai_element_filter` per category with the parameter list. Use `export_room_data` for rooms — it's faster.
4. **Assemble a table per category.** One sheet per category in the xlsx (e.g., `Doors`, `Windows`, `Rooms`).
5. **Add the key column first** (`UniqueId` by default, or `Mark` if user prefers). Follow with human columns.
6. **Write via local XLSX handling.** Use the available XLSX workflow with the tabular data. Preserve existing sheets the user didn't ask to replace — **never overwrite a full workbook the user cares about**.
7. **Report** rows written, path to the file, and a short note: "UniqueId is in column A. Don't remove it — it's how the push step finds each element."

## Workflow: PUSH (Excel → Revit)

This is the destructive direction. Be strict.

1. **Read the xlsx** via local XLSX handling. Identify headers, key column, data rows.
2. **Validate the sheet.**
   - Key column present and non-empty on every row.
   - No duplicate keys.
   - Types parse (widths are numeric, marks are strings, etc.).
   - If anything fails, show the bad rows and stop.
3. **Resolve each row to a Revit element.** For each key:
   - If `UniqueId`: `ai_element_filter` with `UniqueId == <value>`.
   - If `Mark`: `ai_element_filter` with category + `Mark == <value>`. Fail loudly if two elements share a mark.
   - Collect a set of `(ElementId, parameter, oldValue, newValue)` tuples.
4. **Compute a diff.** For each row, compare sheet value to current Revit value. Keep only the cells that changed.
5. **Show the user a preview** in this format:

   ```
   PUSH PREVIEW — 14 changes across 9 elements

   Doors
     D-101 (Id 742318): Width  900 → 1000 mm
     D-101 (Id 742318): Fire Rating  —  → 60 min
     D-204 (Id 751022): Type  Single-Flush → Double-Flush
   Windows
     W-12  (Id 760411): Head Height  2100 → 2200 mm
   ...

   3 rows in the sheet had no matching element (keys: D-999, D-888, D-777)
   ```

6. **Confirm explicitly.** "Apply these 14 changes to the model?" Wait for yes. No exceptions, not even in auto mode — this edits live BIM data.
7. **Generate the C# push script.** One `Transaction`, one `try/catch`, per-element parameter writes, collect failures. See `references/push-csharp-template.md`.
8. **Send via `send_code_to_revit`.** Check the return value for errors.
9. **Report** actual changes applied vs failed + any post-push anomalies (e.g., values clamped by Revit because of type constraints).

## Workflow: DIFF (compare only)

Same first three steps as PUSH, but instead of applying changes, emit the preview table and stop. Offer to run the actual push or pull after.

Useful at the start of a coordination meeting: "Here's where Excel and Revit disagree — which side is right?"

## Parameter mapping

Excel column headers need to map to Revit parameter names. Common translations are documented in [references/parameter-mappings.md](references/parameter-mappings.md). Use it when:

- The user's sheet has a column like "Width (mm)" that maps to Revit's `Width` parameter in internal-unit feet.
- The user asks about supported parameters for a category.
- You're writing a C# script and need the exact `BuiltInParameter` enum.

When the header doesn't match any known mapping, ask before assuming. Don't silently ignore columns — unmapped columns are usually the most important ones.

## Unit handling

Revit stores all lengths in decimal feet internally. The MCP server usually handles conversion for common metric parameters, but when pushing via `send_code_to_revit` you may be setting raw values.

- If the xlsx column header says `(mm)`: multiply by `0.00328084` to feet when writing.
- If the header says `(ft)`: pass through.
- If unclear: ask. Never guess units — a 10× unit error will rescale every wall in the project.

Restate the unit in every preview and report.

## Guardrails

- **Push is destructive.** Show the preview, ask, run. Even in auto mode.
- **Never overwrite a workbook the user values** without a backup. If the xlsx already exists, either write to a new sheet within it or offer a `_synced` suffix copy.
- **UniqueId > Mark > Id.** State which key you used in every report.
- **Duplicate keys halt the job.** Don't guess which element the user meant.
- **Missing rows are not silent.** Flag keys in the sheet that have no Revit match, and elements in Revit that weren't in the sheet.
- **Don't modify Type parameters from an instance row.** Changing a door's type affects every instance of that type. If the user wants to change type, confirm the scope: this instance only (reassign instance type) vs. the whole type (change type's parameter).
- **Large pushes in chunks.** For more than ~200 elements, split transactions to keep Revit responsive and make rollback possible.

## Common recipes

**"Keep door schedule in sync with Excel" (most common ask)**
- First run: PULL doors → `doors.xlsx` with `Mark, Family, Type, Width (mm), Height (mm), Fire Rating, Level, Room From, Room To`.
- Ongoing: user edits the sheet → PUSH updates back. Width/height changes flow through.

**"Bulk-rename marks from a numbered sheet"**
- PUSH with only the `Mark` column in play. No type or width changes.

**"Which rooms exist in the model but not in the Excel schedule?"**
- DIFF on rooms by `Number`. Surface the missing set.

**"Give me a BOQ spreadsheet"**
- PULL walls, floors, doors, windows, columns. One sheet per category. Include quantities column (Area or Volume) where meaningful.

## Notes on combining with other skills

- After a PULL, the same XLSX handling workflow can take over for any further spreadsheet manipulation (formulas, formatting, charts).
- After a PUSH, run `model-audit` to confirm the model state.
- For exotic writes (e.g., modifying shared parameters, writing to project info), fall through to `revit-code-runner` directly.
