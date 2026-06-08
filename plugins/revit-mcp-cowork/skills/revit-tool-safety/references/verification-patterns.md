# Verification Patterns — C# Snippets for `send_code_to_revit`

Ready-to-run snippets for accurate counting, cross-verification, health checks, and any operation where the built-in tools are unreliable. Every snippet returns small, unit-normalized JSON-friendly objects.

**Usage**: pass the snippet as the `code` parameter to `send_code_to_revit` with `transactionMode: "auto"` for mutations or `"auto"` (same) for reads — the wrapper executes inside a transaction either way. Parse the response's `result` field as JSON (it's double-encoded — call `JSON.parse` on the string).

## Connection health check (replaces blocking `say_hello`)

```csharp
return new {
    ok = true,
    title = document?.Title ?? "(no document)",
    viewName = document?.ActiveView?.Name ?? "(no view)",
    viewType = document?.ActiveView?.ViewType.ToString() ?? "(none)",
    revitVersion = document?.Application?.VersionNumber ?? "(unknown)",
    levelCount = new FilteredElementCollector(document)
        .OfClass(typeof(Level))
        .GetElementCount()
};
```

Fast, non-blocking, confirms a document is open and the bridge is responsive. Use at every session start and before any heavy operation.

## Accurate category count

```csharp
using Autodesk.Revit.DB;

var cat = BuiltInCategory.OST_Doors; // change as needed
var count = new FilteredElementCollector(document)
    .OfCategory(cat)
    .WhereElementIsNotElementType()
    .GetElementCount();

return new { category = cat.ToString(), count };
```

Replace `OST_Doors` with the target category. Use this in place of `ai_element_filter` length for every "how many X" question.

## Multi-category count (one call, many categories)

```csharp
using Autodesk.Revit.DB;
using System.Collections.Generic;

var categories = new[] {
    BuiltInCategory.OST_Walls,
    BuiltInCategory.OST_Doors,
    BuiltInCategory.OST_Windows,
    BuiltInCategory.OST_Floors,
    BuiltInCategory.OST_Rooms,
    BuiltInCategory.OST_StructuralFraming,
    BuiltInCategory.OST_StructuralColumns,
    BuiltInCategory.OST_Grids,
    BuiltInCategory.OST_Levels
};

var result = new Dictionary<string, int>();
foreach (var c in categories) {
    result[c.ToString()] = new FilteredElementCollector(document)
        .OfCategory(c)
        .WhereElementIsNotElementType()
        .GetElementCount();
}

return result;
```

One call, one transaction, full breakdown. Cheaper than N separate `ai_element_filter` calls.

## Cross-verify `analyze_model_statistics`

If `analyze_model_statistics` says "142 doors" and you want an independent check:

```csharp
using Autodesk.Revit.DB;

var stats = new {
    doorsWithTypeFilter = new FilteredElementCollector(document)
        .OfCategory(BuiltInCategory.OST_Doors)
        .WhereElementIsNotElementType()
        .GetElementCount(),
    doorsIncludingTypes = new FilteredElementCollector(document)
        .OfCategory(BuiltInCategory.OST_Doors)
        .GetElementCount()
};

return stats;
```

`WhereElementIsNotElementType()` is what `analyze_model_statistics` uses. Matching means both tools agree.

## Filter + count (beyond `analyze_model_statistics`)

`analyze_model_statistics` gives per-category counts. For filtered counts (e.g., "doors on Level 2 with fire rating 60 min"):

```csharp
using Autodesk.Revit.DB;
using System.Linq;

var level = new FilteredElementCollector(document)
    .OfClass(typeof(Level))
    .Cast<Level>()
    .FirstOrDefault(l => l.Name == "Level 2");

if (level == null) return new { error = "Level 2 not found", count = 0 };

var count = new FilteredElementCollector(document)
    .OfCategory(BuiltInCategory.OST_Doors)
    .WhereElementIsNotElementType()
    .Cast<FamilyInstance>()
    .Where(d => d.LevelId == level.Id &&
                d.Symbol.LookupParameter("Fire Rating")?.AsString() == "60 min")
    .Count();

return new { level = "Level 2", fireRating = "60 min", count };
```

## Paginated element list (when you need detail beyond counts)

When `ai_element_filter` with `maxElements: 100000` is still risky (very large models), paginate server-side:

```csharp
using Autodesk.Revit.DB;
using System.Linq;

int page = 0;       // set by caller
int pageSize = 500;

var query = new FilteredElementCollector(document)
    .OfCategory(BuiltInCategory.OST_Doors)
    .WhereElementIsNotElementType()
    .Cast<FamilyInstance>()
    .OrderBy(d => d.Id.IntegerValue);

var total = query.Count();
var page0 = query.Skip(page * pageSize).Take(pageSize)
    .Select(d => new {
        id = d.Id.IntegerValue,
        uniqueId = d.UniqueId,
        family = d.Symbol.Family.Name,
        type = d.Symbol.Name,
        level = d.LevelId != ElementId.InvalidElementId
            ? (document.GetElement(d.LevelId) as Level)?.Name
            : null,
        mark = d.LookupParameter("Mark")?.AsString()
    })
    .ToList();

return new { total, page, pageSize, items = page0 };
```

## Verify type after a `create_*` call

When you place an element and want to confirm the family type matches what you asked for:

```csharp
using Autodesk.Revit.DB;
using System.Linq;
using System.Collections.Generic;

// Replace with the returned element IDs
var createdIds = new List<int> { 742318, 742319, 742320 };
var expectedType = "Single-Flush: 900 x 2134mm";

var mismatches = new List<object>();
foreach (var idInt in createdIds) {
    var e = document.GetElement(new ElementId(idInt)) as FamilyInstance;
    if (e == null) { mismatches.Add(new { id = idInt, issue = "not a FamilyInstance" }); continue; }
    var actual = e.Symbol.Family.Name + ": " + e.Symbol.Name;
    if (actual != expectedType) {
        mismatches.Add(new { id = idInt, expected = expectedType, actual });
    }
}

return new { total = createdIds.Count, mismatchCount = mismatches.Count, mismatches };
```

Zero mismatches → the `create_*` fallback didn't kick in. Report that in the summary.

## Pre / post deletion snapshot (for cascade accounting)

Call before:

```csharp
using Autodesk.Revit.DB;

return new {
    totalElements = new FilteredElementCollector(document)
        .WhereElementIsNotElementType()
        .GetElementCount(),
    doors = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Doors)
        .WhereElementIsNotElementType().GetElementCount(),
    tags = new FilteredElementCollector(document)
        .OfClass(typeof(IndependentTag)).GetElementCount(),
    openings = new FilteredElementCollector(document)
        .OfCategory(BuiltInCategory.OST_Openings)
        .WhereElementIsNotElementType().GetElementCount()
};
```

Call after deletion, diff. Report cascades separately from the direct deletion count.

## Room enclosure check (after `create_room`)

```csharp
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using System.Collections.Generic;
using System.Linq;

var createdIds = new List<int> { /* IDs returned from create_room */ };
var results = new List<object>();

foreach (var idInt in createdIds) {
    var room = document.GetElement(new ElementId(idInt)) as Room;
    if (room == null) continue;
    results.Add(new {
        id = idInt,
        name = room.Name,
        number = room.Number,
        area = room.Area,              // ft²
        areaM2 = room.Area * 0.092903, // normalized
        placed = room.Location != null,
        enclosed = room.Area > 0
    });
}

return new {
    placed = results.Count(r => ((dynamic)r).placed),
    enclosed = results.Count(r => ((dynamic)r).enclosed),
    badlyPlaced = results.Where(r => !((dynamic)r).enclosed).ToList(),
    allRooms = results
};
```

## Detect a view switch after a mutating call

Call before a risky tool (`tag_all_rooms`, `operate_element SelectionBox`):

```csharp
return new {
    viewName = document.ActiveView.Name,
    viewType = document.ActiveView.ViewType.ToString(),
    viewId = document.ActiveView.Id.IntegerValue
};
```

Call the same snippet after. If `viewId` differs, the tool mutated the view. Report to the user.

## Accurate selection count

```csharp
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;

var sel = uidoc.Selection.GetElementIds();
return new {
    count = sel.Count,
    firstTen = sel.Take(10).Select(id => new {
        id = id.IntegerValue,
        name = document.GetElement(id)?.Name,
        category = document.GetElement(id)?.Category?.Name
    }).ToList()
};
```

Don't rely on `get_selected_elements` array length for the total — it caps at 100.

## Unit conversion cheatsheet (for tools returning feet)

| Revit internal | Multiplier for mm | Multiplier for meters |
|---|---|---|
| Length (ft) | × 304.8 | × 0.3048 |
| Area (ft²) | × 92903.04 (→ mm²) | × 0.092903 (→ m²) |
| Volume (ft³) | × 28316846.592 (→ mm³) | × 0.0283168 (→ m³) |

Use when normalizing `export_room_data`, `get_material_quantities`, `analyze_model_statistics.Levels[].Elevation`, `tag_all_walls.tags[].location`, `get_current_view_elements.Properties`.

## Template — safe read-only counting snippet

Every counting script should follow this shape:

```csharp
using Autodesk.Revit.DB;

// 1. Do the query
var n = new FilteredElementCollector(document)
    .OfCategory(BuiltInCategory.OST_Doors)     // replace
    .WhereElementIsNotElementType()
    .GetElementCount();

// 2. Return compact, typed JSON
return new {
    tool = "send_code_to_revit",
    query = "doors, project-wide, instances only",
    count = n,
    revitVersion = document.Application.VersionNumber,
    document = document.Title
};
```

Keep returns small — transport timeouts risk increases with payload size.

## Handling Chinese error strings

Some upstream handlers throw exceptions with Chinese messages. When wrapping errors for the user:

| Chinese fragment | English equivalent |
|---|---|
| `获取元素信息操作超时` | "Get element info operation timed out" |
| `未在项目中找到指定元素` | "No matching element found in the project" |
| `无法将` | "Cannot convert" |
| `警告：无法找到类型` | "Warning: cannot find type" |
| `代码执行超时` | "Code execution timed out" |
| `执行失败` | "Execution failed" |
| `未支持的操作类型` | "Unsupported operation type" |
| `没有有效的元素可以删除` | "No valid elements to delete" |

Translate in your user-facing summary; keep the original for debug logs.
