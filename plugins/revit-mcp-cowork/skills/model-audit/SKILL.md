---
name: model-audit
description: Use when the user asks to "audit the model", "check model health", "give me project stats", "what's in this model", "summarize the current view", "analyze the selection", or wants a QA overview of a Revit document. Produces a structured report on element counts, view/selection context, potential issues, and warnings.
---

# Revit Model Audit

Use this skill when the user wants to understand the current state of a Revit model — for QA, handoff, coordination, or just orientation. Think of it as "ls + du + lint" for a `.rvt` file.

## When this skill applies

- "What's in this model?"
- "Audit the model before we issue for construction."
- "How many walls / doors / rooms are in the current view?"
- "What's selected?"
- "Show me statistics."
- "Is there anything weird in this model?"

> **Critical**: This skill reports numbers to the user. Apply every rule from the `revit-tool-safety` skill. Specifically:
> - Counts come from `analyze_model_statistics` or `send_code_to_revit`, NEVER from `ai_element_filter.Response.length`.
> - If `analyze_model_statistics.Levels[].Elevation` appears in output, convert from feet to mm before displaying.
> - Cross-verify any count the user will act on (issue a model, sign off a schedule).

## Required MCP Tools

- `analyze_model_statistics` — **authoritative** project-wide element counts, category breakdown. No cap, uses server-side `GetElementCount()`.
- `get_current_view_info` — active view name, scale, level, phase, view type.
- `get_current_view_elements` — what's visible in the active view. **Always pass `limit: 100000`**; compare `TotalElementsInView` to `FilteredElementCount` to detect truncation.
- `get_selected_elements` — what the user has selected. **Always pass `limit: 100000`** (default cap is 100 and there is no total field). Cross-verify via a `send_code_to_revit` snippet using `uidoc.Selection.GetElementIds().Count`.
- `send_code_to_revit` — use for any filtered count beyond category (e.g., "doors on Level 2 with fire rating 60 min"). See `revit-tool-safety/references/verification-patterns.md`.
- `ai_element_filter` — **only** for listing detail, never for counting. Always pass `maxElements: 100000`.

## Universal count discipline

Before emitting any count, apply the two-source rule from `revit-tool-safety`:

1. Primary source: `analyze_model_statistics` (always accurate).
2. Secondary source for any count the user will act on: a `send_code_to_revit` snippet like:
   ```csharp
   return new FilteredElementCollector(document)
       .OfCategory(BuiltInCategory.OST_Doors)
       .WhereElementIsNotElementType()
       .GetElementCount();
   ```
3. Only report a number when both sources match. Show both if they differ.

For lists (not counts) pulled via `ai_element_filter` or `get_current_view_elements`, always pass an explicit high limit (`maxElements: 100000` / `limit: 100000`). If the returned array length **exactly** equals the default cap (50, 100), treat it as truncated and re-query.

## Workflow

### 1. Pick the scope

Ask yourself (not the user) what scope makes sense:

- "Audit the model" → full project (`analyze_model_statistics`).
- "What's in this view" → view scope (`get_current_view_info` + `get_current_view_elements`).
- "What's selected" → selection scope (`get_selected_elements`).

If the user's ask is ambiguous, default to **full project** + a note about the current view.

### 2. Pull data

Call tools in parallel when possible — they're read-only. For a full audit, always grab:

1. Project statistics (counts per category)
2. Current view info (so the user knows where Claude is "looking from")
3. Currently selected elements (if any)

### 3. Structure the output

Report in this format (drop sections that aren't relevant):

```
# Revit Model Audit

## Overview
- Project name: <from view_info if available>
- Active view: <name> (<type>, scale 1:<n>)
- Active level: <level>
- Phase: <phase>

## Element counts
| Category | Count |
|---|---|
| Walls | 142 |
| Doors | 38 |
| Windows | 71 |
| Floors | 12 |
| Rooms | 26 |
| Grids | 18 |
| Levels | 5 |
| ... |

## Issues flagged
- 4 rooms are not enclosed (unbounded)
- 12 doors have no tag in the current view
- 3 walls are "Unconnected Height" without a level above
- 1 duplicate grid name ("A")

## Selection
<if something selected: list first 10 elements by category + Id>

## Suggested next steps
- Run document-model to tag untagged doors/rooms
- Run generate-schedule for material takeoff
- Inspect unbounded rooms manually in Revit
```

### 4. Flagging issues

These are worth flagging automatically (use `ai_element_filter` to check):

- Rooms marked "Not Enclosed" or "Redundant"
- Elements at "Unassigned" level/workset
- Duplicate grid or level names
- Walls with `Unconnected Height > 50m` (usually a bug)
- Warnings count (if exposed) — elevated counts are a smell

Don't invent issues. If a check isn't answerable from MCP data, skip it and say so.

### 5. Keep the report concise

A good audit fits on one screen. Truncate long lists. Always include counts and a one-sentence takeaway at the bottom: "Model is healthy," "Needs cleanup before issue," "Missing baseline data."

## For an incremental audit

If the user says "re-audit" or "check again," compare against the previous report if it's in conversation context. Call out what changed — new elements, resolved issues, regressed checks.

## Security / side effects

All tools in this skill are read-only. No model modification. Safe to run anytime.
