---
name: generate-schedule
description: Use when the user asks for a "material takeoff", "quantity takeoff", "BOQ", "bill of quantities", "room schedule", "door schedule", "export rooms", "export model data", "save project info", or wants to extract quantitative data from a Revit model. Produces schedules, takeoffs, and exports, and can store project data for later recall.
---

# Generate Schedules, Takeoffs, and Exports

Use this skill when the user needs numbers out of Revit — quantities, schedules, exported CSVs, or stored project snapshots they can query later. This is the data-extraction side of the plugin.

## When this skill applies

- "Give me a material takeoff for walls and floors"
- "Generate a door schedule"
- "How much concrete is in this building?"
- "Export the room list to CSV"
- "Save this model's data so I can compare it later"
- "Query what we saved for project X"

> **Critical**: apply every rule from the `revit-tool-safety` skill. Schedule-specific gotchas:
> - `get_material_quantities` returns **ft²** and **ft³** — the response does not say so. Always convert (×0.092903 for m², ×0.0283168 for m³).
> - `export_room_data` returns Area in **ft²**, Volume in **ft³**, Perimeter/UnboundedHeight in **ft**. Convert.
> - `export_room_data` has a logic bug: `includeUnplacedRooms` and `includeNotEnclosedRooms` both check `Area == 0` — you can't include one without the other.
> - `store_project_data` upserts on `project_name` only. Multiple projects with the same name **overwrite each other's metadata**. Include a path/GUID suffix in the stored name.
> - `analyze_model_statistics.Levels[].Elevation` is in **feet**. Convert.

## Required MCP Tools

- `get_material_quantities` — volumes, areas, counts by material. Output in **ft²/ft³** — convert. Narrow via `categoryFilters` on large models (10 s C# timeout).
- `export_room_data` — rooms with all parameters. Output in **ft/ft²/ft³** — convert.
- `ai_element_filter` — pass `maxElements: 100000`. For counts, use `analyze_model_statistics` or `send_code_to_revit` instead.
- `analyze_model_statistics` — for accurate per-category counts in a schedule preamble.
- `send_code_to_revit` — for filtered schedules beyond plain categories (see `revit-tool-safety/references/verification-patterns.md` → "Paginated element list").
- `store_project_data` — include a unique suffix in `project_name` to avoid upsert collisions.
- `query_stored_data` — returns everything; filter plugin-side.
- `get_current_view_elements` — pass `limit: 100000` for view-scoped schedules.

## Workflow

### 1. Takeoffs (material quantities)

For "how much of X":

1. Call `get_material_quantities`. This returns per-material volumes, areas, or counts depending on how the material is used.
2. Filter to the materials the user asked about — "concrete" might mean several materials ("Concrete, Cast-in-Place — Concrete," "Concrete — Precast," "Concrete — Masonry"). Sum them and show the breakdown.
3. Report in both SI and imperial if the user's project mixes them, otherwise match project units.

Present as a table:

```
| Material | Volume | Area | Count |
|---|---|---|---|
| Concrete, Cast-in-Place | 142.3 m³ | — | — |
| Gypsum Wall Board | — | 856 m² | — |
| Door: Single Flush 900×2134 | — | — | 38 |
```

### 2. Schedules (element lists)

For "give me a door schedule":

1. Use `ai_element_filter` with category = Doors.
2. Pull the parameters the user cares about — width, height, family, type, level, room. If they didn't specify, include the top 6-8 most useful.
3. Render as a markdown table. If the list is long (> 30 rows), offer to export instead.

Common schedules:

- Door schedule: Family, Type, Width, Height, Level, Room From / To, Mark
- Window schedule: Family, Type, Width, Height, Head Height, Level, Count per type
- Room schedule: `export_room_data` handles this natively — use that tool directly.
- Wall schedule: Type, Length, Area, Level, Fire Rating

### 3. Room data export

`export_room_data` is the one-stop tool for rooms. Call it and format the response. Offer to:

- Show as a markdown table in chat.
- Write to a CSV file in the user's working directory (ask first — writes are a side effect).
- Store as a project snapshot (see next section).

### 4. Storing and querying snapshots

`store_project_data` writes to a local SQLite-style DB the MCP server manages. Use it when the user wants to:

- Compare the model at two points in time ("vs. last week").
- Track quantities across revisions.
- Pin a baseline for coordination meetings.

When storing, give the snapshot a descriptive name + timestamp — e.g., `Project-X_structural_2026-04-21`. Always echo the name back so the user can query it later.

`query_stored_data` reads back. The user might say "show me the snapshots we have" or "compare current walls to the snapshot from last week." Compose the query as narrowly as possible.

### 5. CSV / Excel export

No dedicated CSV-export MCP tool exists. When the user asks to "export to CSV":

1. Pull the data via the relevant tool.
2. Write it to a `.csv` file in the user's working directory using the Write tool (regular file I/O, not the MCP).
3. Confirm the file path and offer to open it.

If the user wants XLSX specifically, hand off to the `anthropic-skills:xlsx` skill with the tabular data in hand.

## Guardrails

- **Numbers must match Revit.** Do not massage, round, or reformat quantities in ways that could lead the user to report different numbers than what Revit shows. State the source (`get_material_quantities`) and let them verify.
- **Unit ambiguity is dangerous in takeoffs.** Always state units explicitly (m³ not "cubic"). Flag if the project mixes metric and imperial.
- **Stored snapshots are local to the machine running the MCP server.** If the user switches machines, old snapshots aren't available. Mention this once if they start using snapshots.
- **A schedule is only as good as the data entered.** If parameters are blank, report them as blank — don't hide empty cells.

## Example conversations

> **User**: "How much concrete do we have?"
>
> **You**: call `get_material_quantities` → filter concrete → report 142 m³ cast-in-place + 18 m³ precast = 160 m³ total. Show the split.

> **User**: "Export the rooms from Level 2."
>
> **You**: call `export_room_data` → filter to Level 2 → show a preview of first 10 rows in chat + offer to write CSV.

> **User**: "Save this as the baseline."
>
> **You**: call `store_project_data` with name `<project>_baseline_<date>` → confirm. Next time they ask "compare to baseline," query it back.
