---
name: document-model
description: Use when the user asks to "tag all walls", "tag all rooms", "add dimensions", "annotate the plan", "create a room", "place rooms", "label elements", or wants to add annotation/documentation elements to a Revit view. Handles bulk tagging, dimensioning, and room placement for construction documentation workflows.
---

# Document a Revit Model

Use this skill when the model geometry is done and the user is preparing documentation — tags, dimensions, room labels. This is the difference between a 3D model and an issuable drawing set.

## When this skill applies

- "Tag all walls in the current view"
- "Tag all rooms"
- "Add dimensions to the south elevation"
- "Place rooms on Level 2"
- "Label every door"
- "Dimension from grid A to grid F"

> **Critical**: apply every rule from the `revit-tool-safety` skill. Doc-specific gotchas:
> - `tag_all_rooms` **silently switches the active view** to a matching floor plan if the current view doesn't match the rooms. Capture `get_current_view_info` before, compare after, and notify the user if `viewSwitched: true`.
> - `create_dimensions.linePoint` defaults to "midpoint offset by 1 foot (304.8 mm)" — pass explicitly when layout matters.
> - `create_room` silently returns success for rooms placed outside enclosed walls (they become unplaced with `Area == 0`). Verify via `export_room_data` after.
> - `tag_all_walls` returns locations in **feet**; `tag_all_rooms` in **mm**. Inconsistent — convert on read.

## Required MCP Tools

- `tag_all_walls` — server command name is `tag_walls`. View-scoped. No wall tag family → entire transaction rolls back.
- `tag_all_rooms` — server command name is `tag_rooms`. **May switch the active view.** Skips already-tagged rooms silently (good).
- `create_dimensions` — pass `linePoint` explicitly.
- `create_room` — verify enclosure after.
- `create_point_based_element` — for non-bulk tag families (door tags, window tags, etc.).
- `get_current_view_info` — capture before/after view-mutating calls.
- `get_current_view_elements` — pass `limit: 100000`.
- `ai_element_filter` — pass `maxElements: 100000`.
- `export_room_data` — to verify rooms were placed correctly (Area > 0). Returns area in **ft²** — convert.

## Workflow

### 1. Bulk tagging

For walls and rooms, the server has dedicated tools. Use them.

- "Tag all walls in this view" → `tag_all_walls`
- "Tag all rooms" → `tag_all_rooms`

These tools tag **only elements in the active view**. Confirm with `get_current_view_info` that the right view is active. If the user wants to tag across multiple views, loop per view and report totals.

For other categories (doors, windows, furniture), use `ai_element_filter` to collect elements, then `create_point_based_element` with the appropriate tag family at each element's location. Mention in the report that "dedicated bulk tag tools don't exist for this category; tagged individually."

### 2. Dimensions

`create_dimensions` takes a set of reference elements (walls, grids, levels) and a dimension line location. Typical patterns:

- **Grid-to-grid dimension string**: collect all grids in one direction, create a horizontal dimension above the view.
- **Wall dimensioning**: one dimension per opening, or overall length per wall.
- **Elevation dimensions**: level-to-level vertical dimensions.

Ask yourself: is the user asking for **overall** dimensions (one big dim) or **incremental** (chained dims between each reference)? Default to chained for grids, overall+chained for walls. State what you're doing.

### 3. Placing rooms

`create_room` takes a point inside an enclosed area on a level. Rules:

- Walls must already form a closed boundary.
- Level must exist.
- Revit will reject room placement outside of bounded areas — if this happens, use `ai_element_filter` to find walls near the point and check for gaps.
- Room name and number default to `Room` and sequential integers. The user may want to rename them after.

For "place a room in every enclosed space on Level 2":

1. `ai_element_filter` to find closed wall loops on Level 2 (or use room bounding heuristic).
2. Compute centroid of each.
3. Call `create_room` for each centroid.
4. Report names / numbers assigned.

### 4. Report format

After bulk operations, give the user:

- Count of tags / dimensions / rooms created.
- The view name(s) affected.
- Any items skipped and why (e.g., "8 doors in this view were already tagged — skipped").
- Next step hint: "Run generate-schedule to produce a room schedule" or "Run find-and-modify to highlight any untagged items."

## Guardrails

- **Never tag in a view where the user didn't ask.** "Tag all walls" means the active view, not every view in the project.
- **Don't re-tag already-tagged elements.** The tools handle this, but mention it in the report so the user knows the count.
- **Room creation can silently create unbounded "bad" rooms.** Always report room count AND flag any rooms that came back with "Not Enclosed" area.
- **Dimensions placed at a dumb location (right on top of the model) are worse than no dimensions.** Pick a sensible offset — typically 2000mm (2m) above grids, 500mm below walls in a plan view.

## Common follow-ups

- After tagging, users often want to export → hand off to `generate-schedule` skill.
- After placing rooms, users often want to color-code by type → hand off to `find-and-modify`.
- After dimensioning, users often want to add text notes → no MCP tool for text notes yet; suggest adding manually in Revit.
