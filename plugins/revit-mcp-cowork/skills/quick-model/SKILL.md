---
name: quick-model
description: Use when the user asks to "place doors", "add windows", "draw walls", "insert furniture", "create a pipe run", "add columns", or wants to add individual building elements to an existing Revit model. Handles point-based (doors/windows/furniture), line-based (walls/beams/pipes/ducts), and surface-based (floors/ceilings) elements from natural-language placement descriptions.
---

# Quick-Model Building Elements

Use this skill when the model already has its shell (levels, grids, maybe walls) and the user wants to add individual elements. Distinct from `scaffold-project` — that's bulk bootstrap; this is targeted placement.

## Decision tree — which tool to call

| What the user wants | Category | MCP tool |
|---|---|---|
| Door, window, column, furniture, generic model, casework, plumbing fixture | Point-based | `create_point_based_element` |
| Wall, beam, pipe, duct, conduit, railing, cable tray | Line-based | `create_line_based_element` |
| Floor, ceiling, roof (flat), structural slab | Surface-based | `create_surface_based_element` |

If the user is ambiguous ("add a stair"), ask ONE clarifying question — stairs need start/end points plus a run direction.

> **Critical**: apply every rule from the `revit-tool-safety` skill. Three rules bite hardest here:
> - **Silent family-type fallback**: if your `typeId` isn't found, the handler picks the first available symbol. Verify after every create.
> - **`baseLevel` is a height, not a level ID**: the handler snaps to the nearest existing level. Pull real level elevations via `ai_element_filter` (with `maxElements: 100000`) and pass exact values.
> - **Returned count can be less than input count** on partial success. Always compare `input.length` to `result.length` and warn on mismatch.

## Required MCP Tools

- `get_available_family_types` — **always call this first** with `limit: 100000` (default is 100 and **has no total field** — truncation is invisible). Does NOT include system types like PipeType, DuctType, RailingType, StairType — fall through to `send_code_to_revit` for those.
- `ai_element_filter` — to get exact level elevations. **Always pass `maxElements: 100000`**.
- `create_point_based_element`
- `create_line_based_element`
- `create_surface_based_element` — outer loop only; no holes (use `send_code_to_revit` if you need cutouts).
- `get_current_view_info` — to know what view / level / plane you're placing in.
- `get_selected_elements` — pass `limit: 100000`. No total field — use `send_code_to_revit` with `uidoc.Selection.GetElementIds().Count` if the full count matters.
- `send_code_to_revit` — to verify placements match requested type after create.

## Workflow

### 1. Inspect before you create

Before placing anything, call `get_available_family_types` filtered by the category the user mentioned. The user often says "add a door" — there might be 15 door types loaded. Either:

- Use the family the user explicitly named.
- Or pick a sensible default (e.g., `Single-Flush: 900 x 2134mm` for generic doors) and state which one you chose.

Then call `get_current_view_info` to confirm the active view, host level, and view scale. Placement coordinates are meaningful only relative to a host — placing a point element in a 3D view without a host level will fail.

### 2. Resolve placement coordinates

The user will say things like "near grid B2" or "in the middle of the south wall." You need to convert these to the (x, y, z) coordinates the MCP tool expects.

- If the user points at a grid intersection, call `ai_element_filter` or `get_current_view_elements` to find grid elements and compute the intersection.
- If they say "on wall X", get the wall's curve endpoints via `get_current_view_elements` and interpolate.
- If they give explicit coordinates, pass them through.
- If underspecified, pick a spot and tell them where — e.g., "placing door 1.5m from the north end of wall A."

### 3. Host considerations

- **Doors and windows** must be hosted on a wall. Check the wall exists and is long enough.
- **Point-based furniture** needs a level but no wall host.
- **Floors/ceilings/roofs** need a closed boundary of points.
- **Beams** need two endpoints and a host level.

### 4. Batch placements

If the user asks for something repetitive ("add a door on every room," "place a column at every grid intersection"), do not loop skill invocations — prefer one logical operation per tool call, but issue the tool calls in rapid sequence. Report a single summary after the batch, not one line per element.

### 5. After creation — always verify

Every `create_*` response gives back element IDs. **Verify**:

1. **Count match**: did `result.length === input.length`? If not, some elements failed silently. Report the gap.
2. **Type match**: use `send_code_to_revit` (template in `revit-tool-safety/references/verification-patterns.md` under "Verify type after a create_* call") to confirm each created element's actual family:type matches what was requested. Report zero-mismatch as "✔ all 14 match requested type" in the summary.
3. **Level placement**: if `baseLevel` mattered, verify the element's `LevelId` resolves to the level the user asked for — not a nearest-neighbor snap.

Then report:

- Count placed / count requested + family:type used (actual, not just requested).
- A one-line summary of where they went.
- Any silent substitutions or level snaps, explicit and upfront.
- If the placement is visible only in a specific view, tell the user which view to open.
- Suggest the next natural step (tagging, dimensioning, material takeoff) and which skill handles it.

## Guardrails

- **Never place an element without a level or host.** Fail loudly and ask rather than guess.
- **If a requested family isn't loaded**, say so and suggest either loading the family or using an available substitute — never invent a family name.
- **Watch for duplicate placement.** If the user says "add a door" and the active view already shows a door in that spot, flag it.
- **Respect the units** — the MCP server usually expects mm. State units in your confirmation.

## Example translations

- "Place a door at the center of the east wall on Level 1" → find wall, midpoint, `create_point_based_element` with door family.
- "Run a line of windows 1.5m apart along the south facade" → parse facade wall, step along it, one `create_point_based_element` per window.
- "Add a beam from grid A1 to grid A5 at Roof level" → `create_line_based_element`, structural framing.
- "Close off this room with a ceiling" → identify room boundary, `create_surface_based_element` with a ceiling type.
