# Revit MCP Next Tool Map

Platform contract: native Windows 11 with Autodesk Revit 2024 on the same
desktop. macOS, Linux, WSL, containers, and remote bridge hosts are unsupported.

Use the MCP server's live tool schemas as authoritative. This map is for fast
routing and was aligned with `BhaveshY/revit-mcp-next` commit `2813df4`.

## Preflight and discovery

- `revit.status`: lightweight connection, document guards, queue, and preview diagnostics.
- `revit.read_bundle`: compact multi-read workflow preflight.
- `revit.list_documents`: open document inventory.
- `revit.get_model_readiness`: scenario prerequisites.
- `revit.catalog`: element types, family symbols, title blocks, view-family, text, dimension, and tag types.
- `revit.describe_parameters`: writable parameter discovery; default to `writableEdit`.

## Bounded reads

- Model: `revit.get_levels`, `revit.query`, `revit.get_current_view_elements`, `revit.get_selection`.
- Context: `revit.get_current_view`, `revit.get_model_context`, `revit.analyze_model`.
- Health/data: `revit.get_warnings`, `revit.get_material_quantities`, `revit.get_rooms`.
- Documentation: `revit.get_views`, `revit.get_sheets`, `revit.get_schedules`, `revit.get_schedule_fields`.

Prefer explicit fields, compact presets, low limits, and opaque cursor paging.
Returned page length is not an exact model count.

## Writes

- Plan: `revit.preview_change_set`.
- Commit: `revit.apply_change_set` with exact preview metadata and operations.
- Recovery: `revit.cancel_request` only for queued/cancellable work; inspect status diagnostics first.

Do not bypass preview/apply. The companion MCP server also exposes discovery
resources/prompts; use them when a live tool description is needed.
