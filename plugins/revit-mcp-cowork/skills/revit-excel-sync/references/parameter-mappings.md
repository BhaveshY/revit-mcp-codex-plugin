# Parameter Mappings — Excel Headers ↔ Revit Parameters

Use this reference to translate between the column names architects use in spreadsheets and the exact parameter names + `BuiltInParameter` enums in the Revit API.

## How to read this

Each table has four columns:

- **Excel header** — common spreadsheet label (with accepted aliases).
- **Revit parameter** — the display name as Revit shows it in Properties.
- **BuiltInParameter** — the enum constant to use when writing C# for `send_code_to_revit`.
- **Type / unit** — value type and unit Revit stores internally. Convert from sheet units accordingly (mm→ft: ×0.00328084).

When the sheet header doesn't match any row here, ask the user. Never guess.

## Doors

| Excel header | Revit parameter | BuiltInParameter | Type / unit |
|---|---|---|---|
| Mark | Mark | `ALL_MODEL_MARK` | string |
| Width (mm) / Width | Width | `DOOR_WIDTH` (type) / `INSTANCE_HEAD_HEIGHT_PARAM` (not applicable) | length (ft) — type-level |
| Height (mm) / Height | Height | `DOOR_HEIGHT` (type) | length (ft) — type-level |
| Head Height (mm) | Head Height | `INSTANCE_HEAD_HEIGHT_PARAM` | length (ft) |
| Sill Height (mm) | Sill Height | `INSTANCE_SILL_HEIGHT_PARAM` | length (ft) |
| Level | Level | `FAMILY_LEVEL_PARAM` | ElementId (Level) |
| Family | Family | read-only derived | string |
| Type | Type | read-only derived | string |
| Fire Rating | Fire Rating | `DOOR_FIRE_RATING` (type) | string (e.g., "60 min") |
| Room From | From Room | `DOOR_FROM_ROOM` | read-only |
| Room To | To Room | `DOOR_TO_ROOM` | read-only |
| Comments | Comments | `ALL_MODEL_INSTANCE_COMMENTS` | string |

**Important**: Width, Height, and Fire Rating are **type parameters** — changing them affects every instance of that type, not just the one row. If the sheet wants per-instance widths, you need per-instance types (one type per unique width). Warn the user.

## Windows

| Excel header | Revit parameter | BuiltInParameter | Type / unit |
|---|---|---|---|
| Mark | Mark | `ALL_MODEL_MARK` | string |
| Width (mm) | Width | `WINDOW_WIDTH` (type) | length (ft) |
| Height (mm) | Height | `WINDOW_HEIGHT` (type) | length (ft) |
| Head Height (mm) | Head Height | `INSTANCE_HEAD_HEIGHT_PARAM` | length (ft) |
| Sill Height (mm) | Sill Height | `INSTANCE_SILL_HEIGHT_PARAM` | length (ft) |
| Level | Level | `FAMILY_LEVEL_PARAM` | ElementId (Level) |
| Family | Family | read-only derived | string |
| Type | Type | read-only derived | string |
| Comments | Comments | `ALL_MODEL_INSTANCE_COMMENTS` | string |

## Walls

| Excel header | Revit parameter | BuiltInParameter | Type / unit |
|---|---|---|---|
| Mark | Mark | `ALL_MODEL_MARK` | string |
| Type Name | Type Name | read-only derived | string |
| Unconnected Height (mm) | Unconnected Height | `WALL_USER_HEIGHT_PARAM` | length (ft) |
| Base Offset (mm) | Base Offset | `WALL_BASE_OFFSET` | length (ft) |
| Top Offset (mm) | Top Offset | `WALL_TOP_OFFSET` | length (ft) |
| Base Constraint | Base Constraint | `WALL_BASE_CONSTRAINT` | ElementId (Level) |
| Top Constraint | Top Constraint | `WALL_HEIGHT_TYPE` | ElementId (Level) or "Unconnected" |
| Length (mm) | Length | `CURVE_ELEM_LENGTH` | length (ft) — read-only |
| Area (m²) | Area | `HOST_AREA_COMPUTED` | area — read-only |
| Volume (m³) | Volume | `HOST_VOLUME_COMPUTED` | volume — read-only |
| Fire Rating | Fire Rating | `FIRE_RATING` (type) | string |
| Function | Function | `FUNCTION_PARAM` (type) | enum (Exterior / Interior / Foundation / Retaining / Soffit / Core-shaft) |
| Structural | Structural | `WALL_STRUCTURAL_USAGE_PARAM` | bool |
| Comments | Comments | `ALL_MODEL_INSTANCE_COMMENTS` | string |

## Rooms

| Excel header | Revit parameter | BuiltInParameter | Type / unit |
|---|---|---|---|
| Number | Number | `ROOM_NUMBER` | string |
| Name | Name | `ROOM_NAME` | string |
| Level | Level | `ROOM_LEVEL_ID` | ElementId (Level) |
| Area (m²) | Area | `ROOM_AREA` | area — read-only |
| Perimeter (mm) | Perimeter | `ROOM_PERIMETER` | length — read-only |
| Volume (m³) | Volume | `ROOM_VOLUME` | volume — read-only |
| Department | Department | `ROOM_DEPARTMENT` | string |
| Occupancy | Occupancy | `ROOM_OCCUPANCY` | string |
| Comments | Comments | `ROOM_COMMENTS` | string |
| Phase | Phase | `ROOM_PHASE` | ElementId (Phase) — read-only |

## Floors / Ceilings / Roofs

| Excel header | Revit parameter | BuiltInParameter | Type / unit |
|---|---|---|---|
| Mark | Mark | `ALL_MODEL_MARK` | string |
| Type Name | Type Name | read-only derived | string |
| Level | Level | `LEVEL_PARAM` (floors) / `LEVEL_PARAM` (ceilings) | ElementId |
| Height Offset From Level (mm) | Height Offset | `FLOOR_HEIGHTABOVELEVEL_PARAM` | length (ft) |
| Area (m²) | Area | `HOST_AREA_COMPUTED` | area — read-only |
| Volume (m³) | Volume | `HOST_VOLUME_COMPUTED` | volume — read-only |
| Perimeter (mm) | Perimeter | `HOST_PERIMETER_COMPUTED` | length — read-only |
| Comments | Comments | `ALL_MODEL_INSTANCE_COMMENTS` | string |

## Columns (Architectural & Structural)

| Excel header | Revit parameter | BuiltInParameter | Type / unit |
|---|---|---|---|
| Mark | Mark | `ALL_MODEL_MARK` | string |
| Type Name | Type Name | read-only derived | string |
| Base Level | Base Level | `FAMILY_BASE_LEVEL_PARAM` | ElementId |
| Base Offset (mm) | Base Offset | `FAMILY_BASE_LEVEL_OFFSET_PARAM` | length (ft) |
| Top Level | Top Level | `FAMILY_TOP_LEVEL_PARAM` | ElementId |
| Top Offset (mm) | Top Offset | `FAMILY_TOP_LEVEL_OFFSET_PARAM` | length (ft) |

## Structural Framing (Beams)

| Excel header | Revit parameter | BuiltInParameter | Type / unit |
|---|---|---|---|
| Mark | Mark | `ALL_MODEL_MARK` | string |
| Type Name | Type Name | read-only derived | string |
| Reference Level | Reference Level | `INSTANCE_REFERENCE_LEVEL_PARAM` | ElementId |
| Start Level Offset (mm) | Start Level Offset | `STRUCTURAL_BEAM_END0_ELEVATION` | length (ft) |
| End Level Offset (mm) | End Level Offset | `STRUCTURAL_BEAM_END1_ELEVATION` | length (ft) |
| Cut Length (mm) | Cut Length | `STRUCTURAL_FRAME_CUT_LENGTH` | length — read-only |

## Universal / project-wide

| Excel header | Revit parameter | BuiltInParameter | Type / unit |
|---|---|---|---|
| UniqueId | (hidden) | `Element.UniqueId` property | string (GUID) — **the best sync key** |
| Id | (hidden) | `Element.Id` | integer — session-local only |
| Phase Created | Phase Created | `PHASE_CREATED` | ElementId (Phase) |
| Phase Demolished | Phase Demolished | `PHASE_DEMOLISHED` | ElementId (Phase) |
| Workset | Workset | (via WorksetId) | string |

## Shared parameters

Project-specific shared parameters don't have `BuiltInParameter` enums — access them by name via `element.LookupParameter("My Param Name")`. When the user's sheet has a custom column that isn't in these tables, treat it as a shared parameter by default. If `LookupParameter` returns null, the parameter doesn't exist on that element; flag and skip.

## Unit conversion cheatsheet

| From | To feet (Revit internal) | Factor |
|---|---|---|
| Millimeters (mm) | feet | × 0.00328084 |
| Meters (m) | feet | × 3.28084 |
| Inches (in) | feet | × 0.0833333 |
| Feet (ft) | feet | × 1 |

For areas: feet² = mm² × 1.07639e-5, m² × 10.7639.
For volumes: feet³ = mm³ × 3.5315e-8, m³ × 35.3147.

Always restate the assumed unit in previews and reports.
