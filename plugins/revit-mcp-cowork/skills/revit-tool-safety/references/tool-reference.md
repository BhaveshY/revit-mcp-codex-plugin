# Revit MCP Tool Reference — Source-Verified

Every tool exposed by `mcp-servers-for-revit`, with its real defaults, limits, units, silent behaviors, and workarounds. This reference was compiled from a source-level audit of the repo (server/src/tools/, commandset/Services/, commandset/Models/). Do not trust the upstream tool descriptions — they lie by omission.

## Read / list tools

### `ai_element_filter`
- **Input**: `filterCategory?`, `filterElementType?`, `filterFamilySymbolId?`, `includeTypes=false`, `includeInstances=true`, `filterVisibleInCurrentView?`, `boundingBoxMin?`, `boundingBoxMax?`, `maxElements?` (default **50**, no hard ceiling).
- **Hard cap**: default `maxElements=50`. The C# side enforces `Take(maxElements)`. **Always pass `maxElements: 100000`** to disable the cap.
- **Silent truncation**: YES. After `Take()`, the handler appends a Chinese message `"X of X"` — but because the Take already reduced the list, X is always `maxElements`, not the true match count. Truncation is effectively invisible.
- **Units**: everything in mm, mm², mm³ (server converts from Revit-internal feet).
- **Return shape**: heterogeneous array — 7 different shape constructors depending on element type (MaterialQuantities / ElementType / Level+Grid / Room+Area / View / Annotation / Group+Link / fallback).
- **Quirks**:
  - Error messages in Chinese.
  - Elements that fail per-shape construction are silently returned as `null` → total `Response.length` can be less than intended.
  - `filterCategory` is case-insensitive; `filterElementType` is case-sensitive.
  - Bounding-box schema is broken (Zod asks `{p0,p1}`, C# reads only `p0`).
- **Use for**: detailed listings with parameters. **Not for counting.**

### `get_current_view_elements`
- **Input**: `modelCategoryList?`, `annotationCategoryList?`, `includeHidden=false`, `limit?` (default **100**).
- **Hard cap**: default `limit=100`. `||` instead of `??` means `limit: 0` falls through to 100.
- **Silent truncation**: partial — response includes `TotalElementsInView` and `FilteredElementCount`. Compare them.
- **Units**: location / start / end in **feet**, stringified with `F2`.
- **Return shape**: `{ ViewId, ViewName, TotalElementsInView, FilteredElementCount, Elements: [{ Id, UniqueId, Name, Category, Properties: Dictionary<string,string> }] }`.
- **Quirks**:
  - `Properties` excludes read-only parameters, so `Level` and `Type` are often absent.
  - Default categories branch is unreachable through TS (always sends empty arrays).
  - On exception, shows a blocking `TaskDialog` in Revit.
- **Use for**: view-scoped inventories. Pass `limit: 100000`.

### `get_available_family_types`
- **Input**: `categoryList?`, `familyNameFilter?`, `limit?` (default **100**).
- **Hard cap**: default `limit=100`.
- **Silent truncation**: YES. **No total count field** — truncation is completely invisible unless you count and it equals exactly 100.
- **Return shape**: `FamilyTypeInfo[]` with `FamilyTypeId, UniqueId, FamilyName, TypeName, Category`.
- **Quirks**:
  - Includes only loadable FamilySymbols + WallType, FloorType, RoofType, CeilingType, CurtainSystemType. **Does not include** PipeType, DuctType, RailingType, StairType, etc. — those are invisible to this tool.
  - `familyNameFilter` matches case-insensitive on family name AND type name.
  - 12.5 s C# timeout (vs 10 s default).
- **Use for**: deciding a type for `create_*`. Pass `limit: 100000`. For system types not in the hard-coded 5, use `send_code_to_revit`.

### `get_selected_elements`
- **Input**: `limit?` (default **100**).
- **Hard cap**: default `limit=100`.
- **Silent truncation**: YES. **No total count field.** If the user selected 500 walls and this tool returns 100, the AI cannot know 400 are missing.
- **Return shape**: thin — `[{ Id, UniqueId, Name, Category }]`. No bounding box, no parameters, no level.
- **Use for**: "what's selected right now." Pass `limit: 100000`, or verify total via `send_code_to_revit` with `uiDoc.Selection.GetElementIds().Count`.

### `get_current_view_info`
- **Input**: none.
- **Hard cap**: n/a.
- **Silent truncation**: no.
- **Return shape**: `{ Id, UniqueId, Name, ViewType, IsTemplate, Scale, DetailLevel }` — minimal.
- **Quirks**: doesn't include `AssociatedLevel`, `CropBox`, `Phase`, `IsActive` — despite the `ViewInfo` shape in `ai_element_filter` including them. Use that instead if you need those fields.
- **Use for**: identifying the active view, scale, detail level. Safe.

### `get_material_quantities`
- **Input**: `categoryFilters?`, `selectedElementsOnly=false`.
- **Hard cap**: none on output. 10 s C# timeout — can exceed this on 10k+ element models.
- **Silent truncation**: no.
- **Units**: Area in **ft²**, Volume in **ft³**. Convert: m² = ft² × 0.092903; m³ = ft³ × 0.0283168.
- **Return shape**: `{ TotalMaterials, TotalArea, TotalVolume, Materials: [{ MaterialId, MaterialName, MaterialClass, Area, Volume, ElementCount, ElementIds: [int] }], Success, Message }`.
- **Quirks**:
  - Unparseable `categoryFilters` silently drop — the filter becomes empty and "all categories" wins.
  - `GetMaterialArea(matId, false)` — the `false` flag means do NOT include material area in painted faces; painted-only materials go missing.
- **Use for**: quantity takeoffs. Always convert units. Narrow via `categoryFilters` on large models.

### `analyze_model_statistics`
- **Input**: `includeDetailedTypes=true`.
- **Hard cap**: **none.** This tool is trustworthy.
- **Silent truncation**: no.
- **Return shape**: `{ ProjectName, TotalElements, TotalTypes, TotalFamilies, TotalViews, TotalSheets, Categories: [{ CategoryName, ElementCount, TypeCount, FamilyCount, Types: [{TypeName, FamilyName, InstanceCount}] }], Levels: [{ LevelName, Elevation, ElementCount }], Success, Message }`.
- **Units**: `Levels[].Elevation` in **feet** (not mm). Convert for display.
- **Quirks**:
  - `TotalFamilies` = distinct family names on `FamilyInstance` only — excludes system-family types.
  - Per-category `Types[]` only populated for `FamilyInstance` elements; walls / floors show empty `Types[]` but correct `ElementCount`.
  - Level-by-level breakdown is O(levels × elements) — can approach the 10 s timeout on 20+ levels × 10k+ elements.
- **Use for**: **this is the authoritative counting tool.** Prefer for any "how many X" question.

### `export_room_data`
- **Input**: `includeUnplacedRooms=false`, `includeNotEnclosedRooms=false`.
- **Hard cap**: none on count.
- **Silent truncation**: no count-side. **Logic bug**: both include flags use the same condition `room.Area == 0`; you can't include unplaced without also including unbounded.
- **Units**: Area in **ft²**, Volume in **ft³**, Perimeter in **ft**, UnboundedHeight in **ft**.
- **Return shape**: `{ TotalRooms, TotalArea, Rooms: [{Id, UniqueId, Name, Number, Level, Area, Volume, Perimeter, UnboundedHeight, Department, Comments, Phase, Occupancy}], Success, Message }`.
- **Quirks**: `Phase` is the phase at which the room was created, not the current phase.
- **Use for**: room schedules. Convert units on read.

## Create / modify tools

### `create_point_based_element`
- **Input**: `data: [{ name, typeId?, locationPoint{x,y,z}, width, depth?, height, baseLevel, baseOffset, rotation?, hostWallId?, facingFlipped=false }]`. **All dimensions in mm.**
- **Silent behavior**:
  - If `typeId` is -1/0/invalid → uses **first available family symbol** in the category. Warning in concatenated message only.
  - `baseLevel` is a **height**, not a level ID — handler calls `FindNearestLevel(baseLevel/304.8)`. Silent snap.
  - If `hostWallId` missing/invalid for a door/window → silently re-hosts on the nearest wall.
- **Error handling**: per-element try/catch; partial success. Returned `elementIds` may be shorter than input — always compare counts.
- **Return shape**: `AIResult<List<int>>` (element IDs).
- **Use with**: explicit `typeId`, explicit `baseLevel` at the true level elevation, and verify post-hoc.

### `create_line_based_element`
- **Input**: `data: [{ category, typeId?, locationLine{p0,p1}, thickness, height, baseLevel, baseOffset }]` (mm).
- Same silent-fallback and level-snap behavior as point.
- `category` is free-form string → `Enum.TryParse<BuiltInCategory>`. Typos become empty filters and silent no-op.

### `create_surface_based_element`
- **Input**: `data: [{ name, category?, typeId?, boundary:{outerLoop:[{p0,p1}] min 3}, thickness, baseLevel, baseOffset }]`.
- **No holes / inner loops** in the schema — requires `send_code_to_revit` for multi-loop profiles.
- Category auto-determined from `typeId` if omitted.

### `create_grid`
- **Input**: `xCount, xSpacing, xStartLabel="A", xNamingStyle="alphabetic"|"numeric"`, same for y, `xExtentMin=0, xExtentMax=50000, yExtentMin=0, yExtentMax=50000, elevation=0, xStartPosition=0, yStartPosition=0`.
- **Silent defaults that change the model**: `xExtentMax=50000, yExtentMax=50000` (mm = 50 m). If you skip extents on a 100 m building, grids are undersized.
- Duplicate grid names are auto-incremented via `GetUniqueGridName`. Silent rename.
- X-axis grids are **vertical lines parallel to Y** (per Revit convention, commonly confusing).

### `create_level`
- **Input**: `data: [{ name, elevation (mm), description?, isMainLevel=true, isBuildingStory=true, computationHeight?, viewPlanOffset?, viewSectionOffset?, viewElevationOffset?, createFloorPlan=true, createCeilingPlan=true }]`.
- **Silent behavior**: if a level with the same name exists, the transaction is rolled back and the returned entry has `AlreadyExisted=true` with the existing level's info. Looks like success — check this flag.

### `create_room`
- **Input**: `data: [{ name, number?, location{x,y,z}, levelId?, upperLimitId?, limitOffset?, baseOffset?, department?, comments? }]` (mm).
- **Silent behavior**:
  - `levelId` missing → uses nearest level to Z coord.
  - Duplicate-number failure preprocessor silently deletes Revit's warning.
  - A room placed at a point not inside enclosed walls silently becomes **unplaced** (`Area == 0`) but the tool returns success.
- Verify with `export_room_data` after and check `Area > 0`.

### `create_dimensions`
- **Input**: `dimensions: [{ startPoint, endPoint, linePoint?, elementIds?, dimensionType="Linear", dimensionStyleId=-1, viewId=-1 }]`.
- `linePoint` defaults to "midpoint offset by 1 foot (304.8 mm)". Pass explicitly when layout matters.

### `create_structural_framing_system`
- **Input**: `levelName (string), xMin/xMax/yMin/yMax, spacing>0, directionEdge="bottom"|"right"|"top"|"left" default "bottom", layoutRule="fixed_distance" (only value accepted), justify="center", beamTypeName?, elevation=0, is3d=false`.
- **Silent behavior**:
  - `levelName` missing but matches `Level N` pattern → **auto-creates the level at 4 m spacing**. Silent model mutation.
  - `beamTypeName` missing → picks the first available structural framing type.
  - `elevation` snaps to nearest existing level.

### `delete_element`
- **Input**: `elementIds: string[]` (strings, parsed to int in C#).
- **Cascades**: `doc.Delete(ids)` in Revit cascade-deletes tags, hosted families, joined wall parts. `DeletedCount` in the response often **exceeds** input length.
- Invalid IDs → blocking `TaskDialog` in Revit. Validate before calling.
- Return: thin — `{ IsSuccess, DeletedCount }`. No per-id success list.

### `operate_element`
- **Input**: `data: { elementIds: number[], action: string, transparencyValue=50, colorValue=[255,0,0] }`.
- **Actions**: `Select`, `SelectionBox`, `SetColor`, `Hide`, `TempHide`, `Isolate`, `Unhide`, `ResetIsolate`, `Delete`, `SetTransparency`. `Highlight` is mentioned in the TS schema but **not implemented** in C# — throws.
- **Silent view mutations**:
  - `SelectionBox` switches to default 3D view if not in 3D.
  - `SetColor` calls `ShowElements` → pans/zooms.
  - Hide/Isolate/SetColor modify the active view's override state; persists across sessions.
- Action strings are case-insensitive via `Enum.TryParse`.

### `color_elements` (TS name; server-side command is `color_splash`)
- **Input**: `categoryName, parameterName, useGradient=false, customColors?`.
- View-scoped. Non-modal. Applies solid fill + line colors.
- Elements with no value for the parameter are grouped under the literal `"None"`.

### `tag_all_walls` (server-side: `tag_walls`)
- **Input**: `useLeader=false, tagTypeId?`.
- View-scoped. Tag at wall midpoint (`Evaluate(0.5, true)`).
- Locations in **feet**.
- No tag family → transaction rolled back.

### `tag_all_rooms` (server-side: `tag_rooms`)
- **Input**: `useLeader=false, tagTypeId?, roomIds?`.
- **Silent view mutation**: if the active view is not FloorPlan/CeilingPlan or is on a different level, the handler switches the active view to a matching floor plan.
- Skips rooms with `Area <= 0` (unplaced) and already-tagged rooms silently.
- Tag locations in **mm** (inconsistent with `tag_all_walls`).
- Returns `viewSwitched: bool` — check and warn the user.

## Custom / advanced

### `send_code_to_revit`
- **Input**: `code: string, parameters?: string[], transactionMode="auto"|"none" default "auto"`.
- **C# timeout**: **60 seconds** (6× the default — suitable for heavy queries).
- **Compiles fresh** with Roslyn on every call, referencing all loaded assemblies in Revit's AppDomain.
- **Return**: `{ success, result, errorMessage }`. **`result` is double-encoded JSON** — parse with `JSON.parse(response.result)`.
- Transaction name `"执行AI代码"` appears in Revit's Undo stack.
- Compile errors → exception with `Line X: message` per diagnostic.
- **Use for**: anything the built-in tools get wrong — accurate counts, custom filters, unit-consistent output, explicit error reporting.

### `say_hello`
- **Input**: `message?: string` (silently ignored — C# never reads it).
- **Blocking modal**: displays a `TaskDialog` that halts Revit's UI until dismissed. **Do not use in automation.**
- For health checks, use `send_code_to_revit` with the ping snippet in `verification-patterns.md`.

## Storage (local SQLite, not Revit)

### `store_project_data`
- Upserts on `project_name` — duplicates collide. Include a GUID/path suffix if running multiple projects with the same name.

### `store_room_data`
- Requires the project to already exist via `store_project_data`.

### `query_stored_data`
- Returns all stored rows with no filter. Potentially large on long-running installs.

## Phantom tools (0-byte files — do not exist at runtime)

- `modify_element`
- `search_modules`
- `use_module`

Never call or mention these.

## Transport quirks

- **Single JSON blob per response** — no length prefix or delimiter. Large responses split across TCP packets can silently stall until the 2-minute socket timeout. For very large returns (>500 KB), prefer multiple smaller calls.
- **Serialized via `ConnectionManager` mutex** — parallel MCP tool calls from the model are sequential. Don't expect concurrency.
- **No retry logic** at the client — build retry-once into the skill flow for transport timeouts.
