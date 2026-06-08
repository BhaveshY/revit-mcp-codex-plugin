---
name: scaffold-project
description: Use when the user asks to "set up a new project", "create levels", "add grids", "scaffold a building", "lay out the structure", "create the building shell", or wants to bootstrap a Revit model with levels, grids, and basic envelope geometry. Creates project datums and a shell of walls, floors, and roofs from a brief description.
---

# Scaffold a Revit Project

Use this skill when the user is starting a new Revit model (or adding to an empty one) and wants to go from zero to a recognizable building shell fast. Typical user asks:

- "Set up a 4-story building, floor-to-floor 3.5m"
- "Add an 8×8 grid, 6m on center both directions"
- "Create the shell — exterior walls on all levels, concrete floors, flat roof"

> **Critical**: apply every rule from the `revit-tool-safety` skill. Gotchas specific to scaffolding:
> - `create_grid` defaults `xExtentMax` and `yExtentMax` to **50 000 mm (50 m)**. Pass explicit extents for buildings larger than 50 m.
> - `create_grid` silently renames duplicate grid names. Check for duplicates before calling.
> - `create_level` returns `AlreadyExisted: true` when a level name collides — the transaction rolled back. Look for this flag; it's not a true success.
> - `get_available_family_types` caps at 100 with **no total field** — always pass `limit: 100000`.

## Required MCP Tools

- `create_level` — batchable; partial success possible. Check `AlreadyExisted` on each result.
- `create_grid` — single transaction (all or nothing). Always pass x/y extents explicitly when the building exceeds 50 m.
- `create_line_based_element` (walls, beams)
- `create_surface_based_element` (floors, ceilings, roofs) — outer loop only.
- `get_available_family_types` — pass `limit: 100000`.
- `ai_element_filter` — pass `maxElements: 100000` to read existing levels/grids before scaffolding (check for collisions).
- `get_current_view_info` — confirm which view is active.
- `analyze_model_statistics` — quick existence check before scaffolding (are there already levels / grids in this project?).

## Workflow

### 1. Confirm what the user wants

Do NOT ask a long list of questions. Extract what was given, assume sensible defaults for the rest, and state the assumptions. Example:

> Going to create 4 levels (Ground at 0, L2 at 3.5m, L3 at 7m, Roof at 10.5m), an 8×8 grid at 6m o.c., and a single wall loop per level using the project's default exterior wall. Say the word if you want different.

Sensible defaults:

- **Levels**: start at 0, floor-to-floor 3000mm (metric) or 10'-0" (imperial) — infer units from the project if possible.
- **Grid spacing**: 6000mm (metric) or 20'-0" (imperial).
- **Wall type**: first exterior wall type returned by `get_available_family_types` for category `Walls`.
- **Floor type**: first generic floor type. Same for roof.

### 2. Create levels first

Call `create_level` once per level. Levels must exist before you can host walls or place grids meaningfully. Name them `Level 1`, `Level 2`, ..., `Roof` unless the user gave names.

### 3. Create grids second

Call `create_grid` for each horizontal and vertical grid line. Letters (A, B, C…) for one direction, numbers (1, 2, 3…) for the other — follow Revit convention.

### 4. Build the shell

For each level except the roof:

1. Use `create_line_based_element` with category `Walls` to draw exterior walls along the grid perimeter.
2. Use `create_surface_based_element` with category `Floors` for the slab above (i.e., slab at the next level up's elevation).

For the top level, use `create_surface_based_element` with category `Roofs`.

### 5. Report back

After creation, call `analyze_model_statistics` (from `model-audit` skill if helpful) and tell the user:

- Number of levels, grids, walls, floors, roofs created.
- The 3D view they should open (or call `get_current_view_info` to confirm).
- What's next — typical follow-ups are openings (`quick-model` skill), rooms (`document-model` skill), or structural framing (`structural-framing` skill).

## Guardrails

- **Never overwrite existing levels/grids silently.** If levels already exist, ask whether to add to or replace them.
- **Units matter.** Revit stores internal units as feet but the user will give you mm or meters. Pass through whatever the MCP tool expects (typically mm for metric projects) and state the unit in your confirmation.
- **Wall justification**: default to wall-center on the grid line unless the user says otherwise. Exterior walls are usually justified to finish face exterior — mention this if the user cares about accuracy.
- **Closed loops only**: walls must form a closed polygon for floors/rooms to work later. Verify the last wall endpoint matches the first.

## If the project is empty of family types

If `get_available_family_types` returns nothing useful (brand new project with no loaded families), tell the user to load families first — Revit's out-of-the-box templates usually include basic wall/floor/roof types, but a blank project will not. Suggest loading `Architectural-Default.rte` template or loading generic families before scaffolding.

## Quick recipes

**"4-story office, 30×60m footprint, 3.5m floor-to-floor":**
```
Levels: L1=0, L2=3500, L3=7000, L4=10500, Roof=14000 (mm)
Grids: A–F at 6000 o.c. (30m / 5 bays), 1–11 at 6000 o.c. (60m / 10 bays)
Walls: exterior perimeter on L1–L4
Floors: slab at L2, L3, L4
Roof: at Roof level
```

**"Residential, 3 floors, 10×15m":**
```
Levels: Ground=0, L2=2800, L3=5600, Roof=8400 (mm)
Grids: A–C at 5000, 1–4 at 5000
Walls + floors + roof: same pattern
```
