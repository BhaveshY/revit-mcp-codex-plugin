# Canonical C# Query Templates — Uncapped, Trustworthy

Every template here is designed to run via `send_code_to_revit` and return complete results with no silent truncation. Use these instead of `ai_element_filter` whenever counts or enumerations matter.

All templates:

- Return a JSON string (parse on the Claude side).
- Complete within the 60-second `send_code_to_revit` timeout.
- Run inside an auto-wrapped read-only scope — no mutations.
- Omit the `using (var t = new Transaction(...))` wrapper because these queries don't modify the model. The `send_code_to_revit` auto-transaction is fine; any `set` operation added later MUST go inside the wrapper.

## 1 — Count all elements of a category

Use for: "How many doors?", "Count of walls," "Number of rooms."

```csharp
using Autodesk.Revit.DB;
using System.Linq;
using System.Text.Json;

// --- Change this ---
var category = BuiltInCategory.OST_Doors;
// -------------------

var count = new FilteredElementCollector(doc)
    .OfCategory(category)
    .WhereElementIsNotElementType()
    .GetElementCount();

return JsonSerializer.Serialize(new { count, category = category.ToString() });
```

Result: `{"count": 142, "category": "OST_Doors"}`. Report as: `142 doors (source: send_code_to_revit canonical count).`

## 2 — Count with parameter criteria

Use for: "How many walls with fire rating 120 min?", "Count of doors on Level 2."

```csharp
using Autodesk.Revit.DB;
using System.Linq;
using System.Text.Json;

// --- Change this ---
var category = BuiltInCategory.OST_Doors;
string paramName = "Level";
string expectedValue = "Level 2";
// -------------------

int count = 0;
var all = new FilteredElementCollector(doc)
    .OfCategory(category)
    .WhereElementIsNotElementType()
    .ToElements();

foreach (var e in all) {
    var p = e.LookupParameter(paramName);
    if (p == null) continue;
    string v = null;
    switch (p.StorageType) {
        case StorageType.String:    v = p.AsString(); break;
        case StorageType.Integer:   v = p.AsInteger().ToString(); break;
        case StorageType.Double:    v = p.AsDouble().ToString(); break;
        case StorageType.ElementId: v = doc.GetElement(p.AsElementId())?.Name; break;
    }
    if (v == expectedValue) count++;
}

return JsonSerializer.Serialize(new {
    count,
    category = category.ToString(),
    criterion = $"{paramName} == \"{expectedValue}\""
});
```

## 3 — Enumerate all elements of a category with parameters

Use for: "List all doors with width and level," "Give me every wall's type and length."

```csharp
using Autodesk.Revit.DB;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

// --- Change this ---
var category = BuiltInCategory.OST_Doors;
var paramsWanted = new[] { "Mark", "Width", "Height", "Level", "Comments" };
// -------------------

var all = new FilteredElementCollector(doc)
    .OfCategory(category)
    .WhereElementIsNotElementType()
    .ToElements();

var rows = new List<Dictionary<string, object>>();
foreach (var e in all) {
    var row = new Dictionary<string, object> {
        ["Id"] = e.Id.IntegerValue,
        ["UniqueId"] = e.UniqueId,
        ["Name"] = e.Name
    };
    foreach (var pn in paramsWanted) {
        var p = e.LookupParameter(pn);
        if (p == null) { row[pn] = null; continue; }
        switch (p.StorageType) {
            case StorageType.String:    row[pn] = p.AsString(); break;
            case StorageType.Integer:   row[pn] = p.AsInteger(); break;
            case StorageType.Double:    row[pn] = UnitUtils.ConvertFromInternalUnits(p.AsDouble(), UnitTypeId.Millimeters); break;
            case StorageType.ElementId: row[pn] = doc.GetElement(p.AsElementId())?.Name; break;
        }
    }
    rows.Add(row);
}

return JsonSerializer.Serialize(new { count = rows.Count, rows });
```

Note the unit conversion — Revit stores lengths in feet internally, this template converts to mm. Change the `UnitTypeId` for other units (`UnitTypeId.Feet`, `UnitTypeId.Meters`, `UnitTypeId.Inches`).

## 4 — Enumerate with parameter filter (uncapped replacement for ai_element_filter)

Use this INSTEAD of `ai_element_filter` whenever the result might exceed 50.

```csharp
using Autodesk.Revit.DB;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

// --- Change this ---
var category = BuiltInCategory.OST_Walls;
string paramName = "Fire Rating";
string expectedValue = "120 min";
var paramsWanted = new[] { "Mark", "Type Name", "Length", "Fire Rating" };
// -------------------

var matching = new FilteredElementCollector(doc)
    .OfCategory(category)
    .WhereElementIsNotElementType()
    .Where(e => e.LookupParameter(paramName)?.AsString() == expectedValue)
    .ToList();

var rows = new List<Dictionary<string, object>>();
foreach (var e in matching) {
    var row = new Dictionary<string, object> {
        ["Id"] = e.Id.IntegerValue,
        ["UniqueId"] = e.UniqueId
    };
    foreach (var pn in paramsWanted) {
        var p = e.LookupParameter(pn);
        row[pn] = p?.StorageType switch {
            StorageType.String    => (object)p.AsString(),
            StorageType.Integer   => p.AsInteger(),
            StorageType.Double    => UnitUtils.ConvertFromInternalUnits(p.AsDouble(), UnitTypeId.Millimeters),
            StorageType.ElementId => doc.GetElement(p.AsElementId())?.Name,
            _ => null
        };
    }
    rows.Add(row);
}

return JsonSerializer.Serialize(new {
    matched = rows.Count,
    category = category.ToString(),
    criterion = $"{paramName} == \"{expectedValue}\"",
    rows
});
```

## 5 — Scoped to current view (uncapped replacement for get_current_view_elements)

Use for: "What's in the active view?", "List everything on this sheet."

```csharp
using Autodesk.Revit.DB;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

// --- Change this ---
var category = BuiltInCategory.OST_Doors; // or null for all categories
// -------------------

var view = doc.ActiveView;
var coll = new FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType();
if (category.HasValue) coll = coll.OfCategory(category.Value);

var all = coll.ToElements();

var rows = all.Select(e => new {
    Id = e.Id.IntegerValue,
    UniqueId = e.UniqueId,
    Name = e.Name,
    Category = e.Category?.Name
}).ToList();

return JsonSerializer.Serialize(new {
    view = view.Name,
    viewType = view.ViewType.ToString(),
    count = rows.Count,
    rows
});
```

## 6 — Scoped to selection (uncapped replacement for get_selected_elements)

Use for: "What's selected?", "Apply X to the selection."

```csharp
using Autodesk.Revit.DB;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

var ids = uidoc.Selection.GetElementIds();
var rows = ids.Select(id => {
    var e = doc.GetElement(id);
    return new {
        Id = id.IntegerValue,
        UniqueId = e?.UniqueId,
        Name = e?.Name,
        Category = e?.Category?.Name
    };
}).ToList();

return JsonSerializer.Serialize(new { count = rows.Count, rows });
```

## 7 — All loaded family types for a category (uncapped replacement for get_available_family_types)

Use for: "What wall types are available?", "List loaded door families."

```csharp
using Autodesk.Revit.DB;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

// --- Change this ---
var category = BuiltInCategory.OST_Walls;
// -------------------

var types = new FilteredElementCollector(doc)
    .OfCategory(category)
    .WhereElementIsElementType()
    .ToElements();

var rows = types.Select(t => new {
    Id = t.Id.IntegerValue,
    Family = (t as ElementType)?.FamilyName,
    Type = t.Name
}).ToList();

return JsonSerializer.Serialize(new {
    count = rows.Count,
    category = category.ToString(),
    rows
});
```

## 8 — Full category breakdown with counts

Redundant with `analyze_model_statistics` but useful if you want a faster, per-category subset.

```csharp
using Autodesk.Revit.DB;
using System.Linq;
using System.Text.Json;

var cats = new[] {
    BuiltInCategory.OST_Walls,
    BuiltInCategory.OST_Doors,
    BuiltInCategory.OST_Windows,
    BuiltInCategory.OST_Floors,
    BuiltInCategory.OST_Rooms,
    BuiltInCategory.OST_Ceilings,
    BuiltInCategory.OST_Roofs,
    BuiltInCategory.OST_Stairs,
    BuiltInCategory.OST_StructuralFraming,
    BuiltInCategory.OST_StructuralColumns,
    BuiltInCategory.OST_Columns,
    BuiltInCategory.OST_Grids,
    BuiltInCategory.OST_Levels
};

var result = cats.ToDictionary(
    c => c.ToString().Replace("OST_", ""),
    c => new FilteredElementCollector(doc).OfCategory(c).WhereElementIsNotElementType().GetElementCount()
);

return JsonSerializer.Serialize(result);
```

## 9 — Common category → `BuiltInCategory` map

A cheat sheet for the category argument in the templates above. User says a word → you pick an enum.

| User says | BuiltInCategory |
|---|---|
| door, doors | `OST_Doors` |
| window, windows | `OST_Windows` |
| wall, walls | `OST_Walls` |
| floor, slab, floors | `OST_Floors` |
| ceiling, ceilings | `OST_Ceilings` |
| roof, roofs | `OST_Roofs` |
| stair, stairs | `OST_Stairs` |
| column, columns (architectural) | `OST_Columns` |
| column, columns (structural) | `OST_StructuralColumns` |
| beam, beams, joist, framing | `OST_StructuralFraming` |
| room, rooms | `OST_Rooms` |
| grid, grids | `OST_Grids` |
| level, levels | `OST_Levels` |
| railing, railings | `OST_StairsRailing` |
| curtain panel | `OST_CurtainWallPanels` |
| curtain wall, mullion | `OST_CurtainWallMullions` |
| pipe, pipes | `OST_PipeCurves` |
| duct, ducts | `OST_DuctCurves` |
| cable tray | `OST_CableTray` |
| conduit | `OST_Conduit` |
| generic model | `OST_GenericModel` |
| casework | `OST_Casework` |
| furniture | `OST_Furniture` |
| plumbing fixture | `OST_PlumbingFixtures` |
| electrical fixture | `OST_ElectricalFixtures` |
| lighting fixture | `OST_LightingFixtures` |

If the user says something not in this table, look it up in `Autodesk.Revit.DB.BuiltInCategory` — don't guess an enum name.

## Output size / timeout guidance

- Counts: < 1 KB response, instant.
- Enumerations with param data for 500+ elements: ~50 KB response, ~2-5s.
- Enumerations for 5000+ elements: may approach the 60s timeout. Split by level or category.
- Enumerations returning > 500 KB can strain the WebSocket bridge. Prefer chunked C# scripts that aggregate counts rather than dump raw data.

When in doubt: run the count script first. If count > 1000, ask the user whether they want a table preview or a csv export — don't silently dump 5000 rows into chat.
