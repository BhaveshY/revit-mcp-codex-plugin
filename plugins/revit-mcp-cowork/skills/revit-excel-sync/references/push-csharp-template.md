# C# Template — Pushing Excel Changes to Revit

Use this template as the starting point when generating C# code for the `send_code_to_revit` tool during a PUSH sync. It handles transaction scope, per-row error isolation, unit conversion, and a clean result string.

## Template

```csharp
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

// ========= EDIT THIS BLOCK PER SYNC RUN =========
// One entry per row that actually has a change.
// keyType: "UniqueId" | "Mark" | "Id"
var changes = new List<(string keyType, string key, string paramName, object newValue, string unit)> {
    ("Mark", "D-101", "Width",          1000.0, "mm"),
    ("Mark", "D-101", "Fire Rating",    "60 min", null),
    ("Mark", "D-204", "Comments",       "Relocated per RFI-14", null),
    // ...
};
var category = BuiltInCategory.OST_Doors; // or OST_Windows, OST_Walls, OST_Rooms, etc.
// ================================================

double MmToFt(double mm) => mm * 0.00328084;
double MtoFt(double m) => m * 3.28084;

Element ResolveByKey(Document d, string kt, string k, BuiltInCategory cat) {
    if (kt == "UniqueId") return d.GetElement(k);
    if (kt == "Id" && int.TryParse(k, out var id)) return d.GetElement(new ElementId(id));
    if (kt == "Mark") {
        return new FilteredElementCollector(d)
            .OfCategory(cat)
            .WhereElementIsNotElementType()
            .FirstOrDefault(e => e.LookupParameter("Mark")?.AsString() == k);
    }
    return null;
}

bool SetValue(Element e, string paramName, object newValue, string unit, out string err) {
    err = null;
    var p = e.LookupParameter(paramName);
    if (p == null) { err = $"no parameter '{paramName}'"; return false; }
    if (p.IsReadOnly) { err = $"'{paramName}' is read-only"; return false; }

    try {
        switch (p.StorageType) {
            case StorageType.Double:
                var d = Convert.ToDouble(newValue);
                if (unit == "mm") d = MmToFt(d);
                else if (unit == "m") d = MtoFt(d);
                p.Set(d);
                return true;
            case StorageType.Integer:
                p.Set(Convert.ToInt32(newValue));
                return true;
            case StorageType.String:
                p.Set(Convert.ToString(newValue));
                return true;
            case StorageType.ElementId:
                // Resolve level/type by name if string given
                if (newValue is string nameStr) {
                    var resolved = new FilteredElementCollector(e.Document)
                        .WhereElementIsNotElementType()
                        .FirstOrDefault(x => x.Name == nameStr);
                    if (resolved == null) { err = $"no element named '{nameStr}' for ElementId param"; return false; }
                    p.Set(resolved.Id);
                } else {
                    p.Set(new ElementId(Convert.ToInt32(newValue)));
                }
                return true;
            default:
                err = $"unsupported storage {p.StorageType}";
                return false;
        }
    } catch (Exception ex) {
        err = ex.Message;
        return false;
    }
}

var sb = new StringBuilder();
int ok = 0, failed = 0, skipped = 0;

using (var t = new Transaction(doc, "Excel → Revit sync")) {
    t.Start();
    foreach (var (kt, k, pname, newVal, unit) in changes) {
        var el = ResolveByKey(doc, kt, k, category);
        if (el == null) { sb.AppendLine($"SKIP [{kt}={k}] not found"); skipped++; continue; }

        if (SetValue(el, pname, newVal, unit, out var err)) {
            sb.AppendLine($"OK   [{kt}={k}] {pname} = {newVal}{(unit != null ? " " + unit : "")}");
            ok++;
        } else {
            sb.AppendLine($"FAIL [{kt}={k}] {pname}: {err}");
            failed++;
        }
    }
    t.Commit();
}

sb.Insert(0, $"Applied {ok}, failed {failed}, skipped {skipped}.\n");
return sb.ToString();
```

## Usage notes

### Building the `changes` list

Before sending the code, build one tuple per **cell that actually changed**. Unchanged cells must be omitted — never re-send a value that's already correct. This keeps transactions small, preserves undo readability, and avoids "modifying document outside of transaction" cascades on read-only derived parameters.

### Category must match the key type

Mark-based resolution is category-scoped. If the batch mixes doors and windows, split into two scripts — one per category — or extend the tuple with its own category field.

### Type parameters vs instance parameters

The template uses `LookupParameter`, which returns an **instance** parameter if one exists, otherwise a type parameter. For a door's `Width` (a type parameter), this will find the type parameter via the type — but setting it will change every instance of that type.

**If you want per-instance values,** you need per-instance types. That's a separate, bigger operation — show a warning and pause for user input.

To explicitly target the type parameter:

```csharp
var typeElem = e.Document.GetElement(e.GetTypeId()) as ElementType;
var p = typeElem.LookupParameter(paramName);
```

To refuse type-level writes and skip them as a safety rail:

```csharp
var p = e.LookupParameter(paramName);
if (p.Definition is InternalDefinition idef && idef.BuiltInParameter.ToString().Contains("_TYPE_")) {
    err = "refusing to set a type parameter from an instance row";
    return false;
}
```

### Level / ElementId parameters

Level names on the Excel sheet need to resolve to an existing `Level` ElementId. The template handles this via a name lookup, but be aware:

- If the sheet has "Level 2" but Revit has "L2", no match — the row fails.
- If two levels share a name, the lookup returns the first, which may be wrong.

Consider pre-normalizing level names with a manual map before generating the script.

### Unit safety

The `unit` field is **per parameter**, not per row. `Width` is mm; `Fire Rating` is a string with no unit. Don't apply mm→ft to a string parameter — the `switch` on `StorageType` prevents that by design, but make sure the `unit` field is `null` for non-length parameters.

### Chunking large pushes

For more than ~200 rows, split into batches to keep the transaction bounded. Revit's undo history compresses contiguous small transactions poorly; huge ones lock the UI and can crash.

```csharp
var batchSize = 100;
for (int i = 0; i < changes.Count; i += batchSize) {
    var batch = changes.Skip(i).Take(batchSize).ToList();
    using (var t = new Transaction(doc, $"Excel → Revit sync ({i}-{i+batch.Count})")) {
        t.Start();
        // process batch...
        t.Commit();
    }
}
```

### Rollback on batch-wide catastrophic failure

The template commits each transaction even if some rows failed — that preserves partial progress. If the user wants all-or-nothing, switch to `t.RollBack()` when `failed > 0` and rerun after fixing the sheet.

### The `doc` and `uidoc` globals

`send_code_to_revit` is expected to expose `doc` (active `Document`) and `uidoc` (`UIDocument`) as globals. If a specific server build doesn't, prepend:

```csharp
var uidoc = commandData.Application.ActiveUIDocument;
var doc = uidoc.Document;
```

### Return value

The script's return string is what the user sees. Lead with a one-line summary, then the per-row log. Keep it parseable — after the run, you may want to feed it back to the xlsx skill to mark rows as synced.
