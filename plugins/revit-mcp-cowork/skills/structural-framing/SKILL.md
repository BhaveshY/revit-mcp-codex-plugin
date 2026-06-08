---
name: structural-framing
description: Use when the user asks to "lay out framing", "create beams", "add a beam grid", "generate a structural framing system", "design a floor framing layout", or wants to build a bay-by-bay beam system in a Revit model. Uses the structural framing generator to place beams across a grid or between supports.
---

# Structural Framing Layouts

Use this skill for structural engineering workflows — laying out beams, joists, or primary framing across bays defined by columns or grids. This is separate from `quick-model` because it operates on **systems** (a whole bay at once) rather than individual members.

## When this skill applies

- "Lay out beams in this bay"
- "Create a framing system, grids A–D, 1–6, joists at 600mm o.c."
- "Add primary and secondary beams between these columns"
- "Generate structural framing for Level 2"
- "Design a typical bay: primary W-beams + secondary joists"

> **Critical**: apply every rule from the `revit-tool-safety` skill. Framing-specific gotchas:
> - `create_structural_framing_system` **silently auto-creates a level** if `levelName` matches the pattern `Level N` and no such level exists — **at 4 m floor-to-floor spacing**. Always verify the level exists first via `ai_element_filter` (with `maxElements: 100000`).
> - `beamTypeName` missing → handler picks the first available structural framing type. Pass an explicit name.
> - `elevation` snaps to the nearest existing level. Explicit `elevation` + `Z_OFFSET_VALUE` sometimes fails silently if the offset parameter is read-only on the beam type.
> - Creating in a non-plan view warns but does not block — the beams land anyway and render weirdly.

## Required MCP Tools

- `create_structural_framing_system` — the main system generator. Always pass `levelName` and `beamTypeName` explicitly.
- `create_line_based_element` — for individual beams not in a system.
- `ai_element_filter` — pass `maxElements: 100000`. Used to find columns, grids, supports and to verify that `levelName` actually exists before framing.
- `get_available_family_types` — pass `limit: 100000`. Structural framing types are included.
- `get_current_view_info` — confirm structural plan view before creation.
- `create_grid` / `create_level` — if the user wants new grids/levels for the framing first.

## Workflow

### 1. Establish the bay

A framing system needs a defined bay — typically bounded by four columns or grid intersections. Ask yourself:

- Did the user say "this bay" while having something selected? → `get_selected_elements` to get the bounding supports.
- Did they give grid labels? → `ai_element_filter` for grids A, D, 1, 6, compute the rectangle.
- Did they specify coordinates? → use as-is.

Report the bay boundaries before placing anything:

> Bay defined by grids A–D (east-west, 18m) × 1–6 (north-south, 30m), at Level 2. Correct?

### 2. Pick the framing strategy

Ask the user (or assume and state) what they want:

- **Primary only**: beams between columns along one direction.
- **Primary + secondary**: primary beams (spanning the short direction), secondary joists at regular spacing perpendicular.
- **All-directions grid**: beams on every grid line.

Typical default: **primary + secondary**, joists at 600mm (2'-0") o.c. perpendicular to the primary. State your assumption.

### 3. Pick the member families

Call `get_available_family_types` for category `Structural Framing`. Pick:

- **Primary**: largest available wide-flange or equivalent (e.g., `W24x68`) unless the user specified.
- **Secondary**: smaller member (e.g., `W12x26` or `W10x22`).

If neither the user nor the project has loaded structural framing families, say so — nothing can be placed without them. Offer to use generic structural framing or ask the user to load families.

### 4. Generate the system

Use `create_structural_framing_system` for the bulk action. If the server's version doesn't support a complete system generator, fall back to a loop of `create_line_based_element` calls with category `Structural Framing`.

Placement order:

1. Primary beams between support columns.
2. Secondary members at the user-specified spacing (default 600mm).
3. If an edge beam is needed on the perimeter, add it explicitly — systems sometimes skip perimeters.

### 5. Report

After generation:

- Count primary + secondary beams placed.
- Total linear length (for a quick takeoff preview).
- The family:type used for each.
- The view to open to verify.
- Warn about any clashes with existing elements (if detectable via `ai_element_filter`).

Offer follow-ups: "Run generate-schedule for a framing takeoff," or "Run model-audit to check total beam count."

## Guardrails

- **Structural elements carry downstream consequences.** Framing placed in a design model might flow into analytical models, load takedowns, or coordination platforms. Never generate at scale without confirming the bay, spacing, and family.
- **Respect existing work.** If beams already exist in the bay, show the user and ask whether to add to or replace.
- **Spacing matters.** Joists too close waste material; too far may fail code (deflection, load). The plugin can't do code checks — state clearly that spacing is a user input, not a design recommendation.
- **Default direction**: primaries span the short direction of a rectangular bay, joists perpendicular, unless the user says otherwise. Always state which.

## Example recipes

**"Standard typical bay, Level 2":**
- Primary: W24x68 on grids 1, 2, 3, 4, 5, 6 (east-west).
- Secondary: W12x26 perpendicular at 600mm o.c.
- Host level: Level 2.

**"Glulam joists for a pavilion":**
- Primary: Glulam 240×600, two lines parallel to long edge.
- Secondary: Glulam 120×300 perpendicular at 800mm.
- Edge beams all around.

**"Precast double-tees":**
- Primary: precast inverted-T beam on supports.
- Secondary: double-tees spanning perpendicular (create one per bay width).
- No separate joists.
