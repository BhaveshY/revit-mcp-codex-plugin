---
name: find-and-modify
description: Use when the user asks to "find elements", "filter", "show me all X", "color-code", "highlight", "hide", "isolate", "select by criteria", "delete all X", or wants to query the model with natural-language criteria and then do something with the results. Combines AI element filtering with visibility, color, and deletion operations.
---

# Find and Modify Elements

Use this skill when the user wants to **query** the model (find specific elements) and then **act** on what they found — color them, hide them, isolate them, delete them, or just list them. This is the "grep + awk" skill for a Revit model.

## When this skill applies

- "Find all walls taller than 4m"
- "Color doors on Level 2 by type"
- "Hide all elements that aren't walls"
- "Show me every column in the structural grid"
- "Delete every generic model element"
- "Isolate rooms marked as circulation"
- "Highlight walls with fire rating < 60 min"

> **Critical**: apply every rule from the `revit-tool-safety` skill. In particular:
> - `ai_element_filter` default caps at 50 — **always pass `maxElements: 100000`**.
> - Counts come from `analyze_model_statistics` / `send_code_to_revit`, not from filter results.
> - `delete_element` cascades — `DeletedCount` can exceed input length. Snapshot before/after.
> - `operate_element` with `SelectionBox` or `SetColor` silently mutates the active view — capture the view name before and notify if changed.
> - `operate_element` has no `Highlight` action despite the TS schema claiming one; don't use it.
> - Visibility overrides from `operate_element` persist across sessions until explicitly reset.

## Required MCP Tools

- `ai_element_filter` — the workhorse; **always** pass `maxElements: 100000`. Bounding-box schema is broken — apply spatial filters plugin-side instead.
- `send_code_to_revit` — for any filter beyond category, or when the match count is critical and must be verified.
- `analyze_model_statistics` — to cross-verify counts before a destructive op.
- `color_elements` — apply override colors in the active view (server command name: `color_splash`).
- `operate_element` — select / hide / isolate / unhide / delete actions. Case-insensitive action strings. **No `Highlight` action exists.**
- `delete_element` — remove by element ID. Cascades — count before and after to report cascades separately.
- `get_current_view_info` — capture before view-mutating operations.

## Workflow

### 1. Find first, act second

The discipline: every action on elements starts with `ai_element_filter`. The user's phrasing usually maps directly — "walls on Level 2 with fire rating 120 min" becomes a filter call with category + parameter constraints.

Describe the filter you built in plain language before you apply an action. If the filter could match too broadly or too narrowly, say so and confirm.

Example:

> Filtering: `category=Walls AND Level=="Level 2" AND "Fire Rating"=="120 min"`. This matches 14 walls. Going to color them orange in the current view. OK?

For non-destructive actions (color, isolate, select), proceed without confirmation. For destructive ones (delete, bulk modification), confirm.

### 2. Visual overrides (color_elements)

`color_elements` changes the graphics override in the active view only — not a permanent property. Use this for:

- **QA highlighting**: color elements that fail a check (e.g., walls missing fire rating).
- **Category visualization**: color-code by type, level, or parameter.
- **Coordination**: highlight elements that interact with another discipline.

Always state:

- Which view got the override.
- That the override is view-specific and non-destructive.
- How to revert (Manage → Reset Graphic Overrides, or call with a "clear" action if supported).

### 3. Visibility (operate_element)

Actions available (depending on server build): `select`, `hide`, `isolate`, `unhide`, `isolateCategory`.

- **Isolate** = hide everything else. Good for focused review.
- **Hide** = hide the filtered elements, keep rest visible.
- **Select** = just select them in Revit so the user can act manually.

Visibility changes, like colors, are view-specific. Mention this.

### 4. Deletion (delete_element) — enterprise-grade

Destructive and cascading. Treat with discipline:

1. Filter via `ai_element_filter` with `maxElements: 100000`.
2. **Cross-verify count** via `send_code_to_revit`:
   ```csharp
   // count matching your filter
   return new FilteredElementCollector(document)
       .OfCategory(BuiltInCategory.OST_GenericModel)
       .WhereElementIsNotElementType()
       .GetElementCount();
   ```
3. Snapshot total-element counts via `analyze_model_statistics` BEFORE deletion — needed to report cascades.
4. Show a sample (first 5 elements by Id + Name).
5. **Explicitly ask the user to confirm**: "Delete 47 generic models project-wide? Revit may cascade-delete dependent elements (tags, hosts). Proceed?"
6. Only on explicit yes, call `delete_element` with the full ID list.
7. Snapshot counts again. Report:
   - Primary deletions: 47 (as requested).
   - Cascade deletions: N (tags, hosts, etc.) — computed as `pre.total - post.total - primaryDeletions`.
   - Total removed: 47 + N.
8. If `DeletedCount` from the tool exceeds 47, state the excess came from cascades.

Never delete without an explicit confirmation. Never report "deleted 47" when the actual removal count differs.

### 5. Combined workflows

Some common combos:

- **"Color by parameter"**: filter → group by parameter value → color each group a different color. State the legend.
- **"Cleanup unused"**: filter unused families → list → confirm → delete. Great for end-of-project hygiene.
- **"Audit visibility"**: filter → `operate_element isolate` → ask user to verify → `unhide` afterward.

## Guardrails

- **Never delete without explicit user confirmation**, even if it feels implied by the request.
- **Never color / hide in a view without reporting which view.** Users can get very confused when colors appear in one view and not another.
- **Don't chain destructive operations without checkpoints.** "Find all X, then delete them, then also delete their tags" — break into steps with confirmations.
- **Selection persists after you disconnect.** If you leave elements selected in Revit and the user starts drawing, they might accidentally modify the selection. Consider clearing selection at the end of a session.

## Filter vocabulary tips

`ai_element_filter` is forgiving but works better with specific criteria. Prefer:

- ✅ `category=Walls, Level="Level 2", Type.contains="CMU"`
- ❌ "find the concrete ones on the second floor"

When translating the user's request, be explicit about:

- **Category** (Walls, Doors, Rooms, Floors, Generic Models, etc.)
- **Parameter constraints** (Fire Rating, Mark, Comments, Level, Phase)
- **Spatial constraints** (in view, on level, in room)
- **Type constraints** (family name, type name)
