---
name: revit-tool-safety
description: Use BEFORE calling any `revit` MCP tool — `ai_element_filter`, `get_current_view_elements`, `get_available_family_types`, `get_selected_elements`, `get_material_quantities`, `analyze_model_statistics`, `export_room_data`, any `create_*`, `delete_element`, `operate_element`, `color_elements`, `tag_all_walls`, `tag_all_rooms`, `send_code_to_revit`, `say_hello`, or any `store_*` / `query_stored_data` call. Use whenever counting, listing, filtering, or reporting element quantities from Revit. Use whenever a user asks "how many X," "list all X," or expects a complete enumeration. Loads the universal safety discipline that prevents silent truncation, unit confusion, cascade surprises, and silent view mutations found in the upstream MCP server.
---

# Revit MCP Tool Safety — Enterprise Discipline

**Read this first, every Revit session.** The upstream `mcp-servers-for-revit` server (as of v0.4.x in our plugin) has a set of hidden caps, silent fallbacks, unit inconsistencies, and side-effects that will cause wrong answers if you use the tools naively. This skill defines the universal discipline that every other skill in this plugin relies on.

This is a **rigid** skill — follow it exactly. Do not rationalize your way out of any rule. Every rule exists because of a specific bug verified in the upstream source.

## The single most important rule

**Never rely on the returned array length from a Revit MCP tool as a count.** Most of the read/list tools silently truncate to 50 or 100 rows. The only trustworthy counts come from `analyze_model_statistics` or a `send_code_to_revit` snippet that calls `FilteredElementCollector(...).GetElementCount()`.

If a user asks "how many doors are there?" — **call `analyze_model_statistics` or `send_code_to_revit`**. Not `ai_element_filter`.

## Universal rules

### Rule 1 — Always pass explicit `limit` / `maxElements`

Every listing tool has a silent default that truncates to a small number:

| Tool | Silent default | Action |
|---|---|---|
| `ai_element_filter` | `maxElements: 50` | **Always pass** `maxElements: 100000` |
| `get_current_view_elements` | `limit: 100` | **Always pass** `limit: 100000` |
| `get_available_family_types` | `limit: 100` | **Always pass** `limit: 100000` |
| `get_selected_elements` | `limit: 100` | **Always pass** `limit: 100000` |

There is no hard ceiling in the C# server — `Take(100000)` just returns everything. Pass 100 000 unless the user explicitly asks for a subset.

### Rule 2 — Counting requires a counting tool

Do not count via `ai_element_filter` or any listing tool, even with a high limit. Use one of:

- **`analyze_model_statistics`** (preferred) — returns per-category `ElementCount` using server-side `GetElementCount()`. No cap, no truncation, fast.
- **`send_code_to_revit`** with `new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Doors).WhereElementIsNotElementType().GetElementCount()` — when you need a filter beyond category.

See [references/verification-patterns.md](references/verification-patterns.md) for ready-to-run verification snippets (counts, cross-verify, cascade, room enclosure, type match, view change, health). See [references/canonical-queries.md](references/canonical-queries.md) for full-enumeration C# templates (all elements of a category with parameters, filtered enumerations, view/selection scope, family-type listings, and the full user-term → `BuiltInCategory` map).

### Rule 3 — Round numbers mean "probably truncated"

If a listing tool returns **exactly** 50, 100, or any default-cap value, treat it as suspect. Re-query with a higher limit, or cross-check the count via `analyze_model_statistics`.

The `ai_element_filter` appended-message bug is real: after `Take(50)`, the handler prints `"50 of 50"` even when the actual match was 142. You cannot trust the text of the message to detect truncation — only the raw count matters.

### Rule 4 — Cross-verify every count you report

Before telling the user "there are N Xs," run at least two independent checks:

1. `analyze_model_statistics` → `Categories.find(c.CategoryName === "Doors").ElementCount`
2. `send_code_to_revit` returning `FilteredElementCollector(...).GetElementCount()`

Report the number only when they match. If they disagree, report both and ask the user which scope they meant (project-wide vs view-visible vs selection).

### Rule 5 — Units are inconsistent across tools; normalize on ingestion

The server is **not** unit-consistent. You must convert on the plugin side.

| Tool / field | Unit returned |
|---|---|
| `ai_element_filter` bounding boxes, level elevation, room volume | **millimeters** (already converted server-side) |
| `export_room_data` `Area` / `Volume` / `Perimeter` / `UnboundedHeight` | **feet, ft², ft³** (no conversion!) |
| `get_material_quantities` `Area` / `Volume` / `TotalArea` / `TotalVolume` | **ft², ft³** (no conversion) |
| `analyze_model_statistics` `Levels[].Elevation` | **feet** (no conversion) |
| `get_current_view_elements` location / start / end | **feet, stringified F2** |
| `tag_all_walls` `tags[].location` | **feet** |
| `tag_all_rooms` `tags[].location` | **millimeters** (inconsistent with tag_all_walls) |

**Always convert feet → mm (×304.8) or ft² → m² (×0.092903) when showing values to the user.** Always state the unit in the final report. Never let a ft-vs-mm mix-up reach the output.

### Rule 6 — Silent family-type fallback on `create_*`

`create_point_based_element`, `create_line_based_element`, `create_surface_based_element`, and `create_structural_framing_system` **silently substitute the first available family symbol** if the requested `typeId` is not found. A warning lands in the returned `message` string — but it's easy to miss.

After every `create_*` call, **verify the created elements match the intended type**:

1. Collect returned `elementIds`.
2. Call `ai_element_filter` (with a per-id bounding-box or a `send_code_to_revit` lookup) to read back each element's actual `TypeName`.
3. If any differ from the intended type, warn the user and offer to delete and retry with an explicit `typeId`.

Do this silently in the background — don't spam the user with verification steps for routine placements, but do include a line in the final summary: "Verified: 14 / 14 match requested type."

### Rule 7 — `baseLevel` is a **height**, not a level ID

On `create_point_based_element`, `create_line_based_element`, and `create_structural_framing_system`, the `baseLevel` parameter is a height in mm, not a level ElementId. The handler calls `doc.FindNearestLevel(baseLevel / 304.8)` and uses the **nearest existing level**. If the nearest level is 400 mm off, your element is 400 mm off — unless `baseOffset` compensates.

**Mitigation**:

1. Before any `create_*` call that takes `baseLevel`, call `ai_element_filter` with `filterElementType: "Level"` (and `maxElements: 100000`) to get the exact elevations of existing levels.
2. Pick the level you actually want.
3. Set `baseLevel` to that level's **exact** elevation (in mm).
4. `baseOffset = 0` unless the user wants an offset.

Do not pass a nominal "Level 2 = 3500" if the actual Level 2 in the project sits at 3487.6 mm. The silent snap will bite.

### Rule 8 — `create_structural_framing_system` can auto-create levels

If you pass `levelName: "Level 5"` and no such level exists but the name matches the `Level N` pattern, the handler **silently creates a new level at 4000 mm spacing**. This is a silent model mutation.

**Mitigation**: always verify the level exists first via `ai_element_filter` before calling `create_structural_framing_system`. If it doesn't exist, ask the user whether to create it at the elevation they want.

### Rule 9 — `delete_element` cascades

Deleting one element can cascade through Revit's dependency graph — tags, hosted families, joined walls, etc. The returned `DeletedCount` includes cascades, so it's often **greater** than the input list length.

**Mitigation** for enterprise workflows:

1. Before deleting, snapshot the current `analyze_model_statistics` element count.
2. Delete.
3. Snapshot again.
4. Report: "Deleted 14 doors as requested. Cascaded deletions: 8 (tags). Total removed: 22."

Never say "deleted 14 elements" when the actual removal count differs.

### Rule 10 — Silent view mutations

These tools **silently change the active Revit view or its graphic overrides**:

- `tag_all_rooms` — switches to a matching floor plan if the current view doesn't match the rooms' level.
- `operate_element` with action `SelectionBox` — switches to a default 3D view and enables the section box.
- `operate_element` with action `SetColor` — calls `ShowElements` which pans/zooms the view.
- `create_structural_framing_system` in a non-plan view — warns but still creates.

**Mitigation**:

1. Before any of these calls, capture the current view name via `get_current_view_info`.
2. After the call, compare. If changed, tell the user explicitly: "Note: the active view was switched from `<old>` to `<new>` during this operation."
3. Visibility overrides from `operate_element` (`Hide`, `Isolate`, `SetColor`, etc.) persist in the view. If the user expects a reset, explicitly call `operate_element` with `action: ResetIsolate` at the end.

### Rule 11 — Health check uses `send_code_to_revit`, not `say_hello`

**Do not call `say_hello` in automation or health checks.** `say_hello` shows a blocking modal `TaskDialog` in Revit that halts the Revit UI until the user dismisses it. In headless or background flows, this will wedge Revit.

Use this ping snippet via `send_code_to_revit` instead:

```csharp
return new { ok = true, title = document?.Title ?? "(no document)", view = document?.ActiveView?.Name ?? "(no view)" };
```

Fast, non-blocking, returns useful context. See [references/verification-patterns.md](references/verification-patterns.md).

### Rule 12 — Error messages are often in Chinese

The upstream server is Chinese-authored; several error strings and transaction names are in Chinese (e.g., `"获取元素信息操作超时"` = "Get element info operation timed out", `"执行AI代码"` = "Execute AI code" transaction name). When surfacing an error to the user:

1. Translate or paraphrase in English.
2. Keep the original string in parentheses for debugging.
3. Do not show the raw Chinese as-is to end users.

### Rule 13 — Retry transport timeouts once

The client has no retry logic. A transient Revit hang produces a 2-minute timeout. For any tool call that times out:

1. Retry **once** with the same parameters.
2. If the retry also times out, stop and surface the failure with a clear message: "The Revit bridge did not respond in 4 minutes across 2 attempts. Common causes: Revit is opening a large file, a modal dialog is showing, or the bridge service crashed. Verify Revit is responsive and call `setup-revit` for the connection-health check."

Never silently retry more than once — repeated hangs suggest a real problem that needs human attention.

### Rule 14 — Phantom tools

These tools appear in the upstream repo tree but are 0-byte files — they do **not** exist at runtime:

- `modify_element`
- `search_modules`
- `use_module`

Never mention them, never call them. If the model is tempted to invoke one, stop and use a real tool (usually `send_code_to_revit` for anything `modify_element`-shaped).

### Rule 15 — `ai_element_filter` bounding box schema is broken

The Zod schema asks for `boundingBoxMin: { p0, p1 }` and `boundingBoxMax: { p0, p1 }`, but the C# side reads only **one coordinate** per object (the implicit root, not `.p0`). Passing `{ p0: ..., p1: ... }` may behave unexpectedly.

**Mitigation**: avoid bounding-box filtering in `ai_element_filter`. Instead, fetch the unfiltered set and apply spatial filtering plugin-side, or use `send_code_to_revit` with explicit `BoundingBoxIntersectsFilter` construction.

### Rule 16 — `delete_element` and `operate_element` throw blocking dialogs on bad input

Passing a non-numeric element ID to `delete_element` or an unsupported action to `operate_element` triggers a modal `TaskDialog` in Revit that halts the UI. Always validate inputs before calling — the MCP call will appear to hang until a human dismisses the dialog.

### Rule 17 — `store_project_data` upsert is name-keyed

The project DB upserts on `project_name`. Two different Revit documents with the same project name **will overwrite each other's stored data**. When using `store_project_data`, include a path or GUID suffix in the project name, or store the distinguishing value in `metadata`.

## Decision tree for common asks

### "How many X are there?" / "Count the Xs"

1. Call `analyze_model_statistics`.
2. Find `Categories.find(c => c.CategoryName === "<X>").ElementCount`.
3. (Optional but recommended) Cross-verify with `send_code_to_revit`:
   ```csharp
   return new FilteredElementCollector(document)
       .OfCategory(BuiltInCategory.OST_<X>)
       .WhereElementIsNotElementType()
       .GetElementCount();
   ```
4. Report the count. If the two sources disagree, show both.

### "List all X" / "Show me the X"

1. If the user needs detail (params, family, type): call `ai_element_filter` with `filterCategory: "OST_<X>"` and `maxElements: 100000`.
2. Compare returned array length to the `analyze_model_statistics` count for sanity.
3. If they differ significantly, explain the discrepancy (usually: types not included, view filter active, phase filter).

### "What's in the current view?"

Call `get_current_view_elements` with `limit: 100000`. Compare `FilteredElementCount` to `TotalElementsInView` — if they differ, state the scope explicitly.

### "What's selected?"

Call `get_selected_elements` with `limit: 100000`. Tell the user the category breakdown. No need to cross-verify — the selection is what it is.

### "Change / create / delete something"

Defer to the relevant skill (`quick-model`, `find-and-modify`, etc.) — but apply Rules 6, 7, 9 from this skill as guardrails.

## What to tell the user after a verified call

Include in the summary:

1. The number reported, with its unit.
2. Which tool produced it (one of: `analyze_model_statistics`, `send_code_to_revit`, etc.).
3. The cross-verification result (match / mismatch).
4. Any truncation, fallback, or mutation warnings.

Example:

> **142 doors** in the project (project-wide).
> Source: `analyze_model_statistics` (142) cross-verified via `send_code_to_revit` (142). ✔ match.
> No truncation, no silent family substitution, active view unchanged.

Compare to the naive (wrong) answer: "50 doors." This discipline is the difference.

## If you cannot apply a rule

Be explicit. If a tool returns something and you cannot verify it (e.g., the server is slow and the verification call times out):

- Do not extrapolate or estimate.
- State the partial finding and the failed verification.
- Offer to retry or narrow the scope.

Accuracy over confidence. Enterprise users correct errors by going back to Revit manually — a wrong number wastes hours.
