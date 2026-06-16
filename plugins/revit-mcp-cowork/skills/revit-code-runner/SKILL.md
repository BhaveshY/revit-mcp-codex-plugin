---
name: revit-code-runner
description: Use when the user asks to "run C# code in Revit", "execute a Revit API script", "write a custom macro", "do something the tools can't", "script this", or wants to perform an operation in Revit that isn't covered by the built-in MCP tools. Sends C# code to Revit via the send_code_to_revit tool for execution inside the Revit API transaction scope.
---

# Revit Code Runner — Custom C# in Revit

Use this skill as the **escape hatch** when none of the other skills covers what the user needs. The `send_code_to_revit` tool executes arbitrary C# inside Revit's API context, giving access to every class in `RevitAPI.dll` and `RevitAPIUI.dll`.

## When this skill applies

- "Write a script that finds all walls taller than X and changes their type."
- "I need to set a parameter on every door based on its room."
- "Automate the Family Type Catalog update."
- "Batch-rename all levels to use a custom format."
- "The built-in tools can't do this — can you write custom code?"

> **Critical**: this skill is also the fallback for every accuracy problem in the other tools. When the upstream MCP tools are wrong, silent, or unit-inconsistent, write C# here and run it. See `revit-tool-safety/references/verification-patterns.md` for ready-to-use snippets (count, cross-verify, cascade snapshot, room enclosure, type match).

## Required MCP Tools

- `send_code_to_revit` — the only tool this skill uses. 60-second C# timeout (longer than other tools). `result` is double-encoded JSON — parse with `JSON.parse`. Transaction name `"执行AI代码"` (Chinese) appears in Revit's Undo stack.

## Workflow

### 1. Confirm that no built-in tool covers the request

Before writing C#, mentally scan the tool inventory:

| Common request | Covered by |
|---|---|
| Create levels / grids | `scaffold-project` skill |
| Place doors / walls / floors | `quick-model` skill |
| Query elements by criteria | `find-and-modify` skill (via `ai_element_filter`) |
| Material takeoff | `generate-schedule` skill |
| Tag / dimension / room | `document-model` skill |
| Color / hide / delete | `find-and-modify` skill |

If any of these already solve it, defer to that skill. Only drop to code when the operation is genuinely custom — bulk parameter manipulation, API calls not exposed as tools, one-off macros.

### 2. Write correct Revit API code

Every script you send must follow Revit API discipline. Non-negotiable rules:

- **All model modifications must be wrapped in a `Transaction`.** Start it, commit it (or roll back on exception), dispose it. Failing to do this raises "Attempt to modify document outside of a transaction."
- **Use the active `Document` and `UIDocument`** — the server typically exposes these as `doc` and `uidoc` globals. If not, retrieve via `commandData.Application.ActiveUIDocument.Document`.
- **Filtered element collectors** are the way to query — `new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType()`.
- **Regenerate after modifications** if the script needs updated geometry: `doc.Regenerate()`.
- **Return a string result** — the MCP tool pipes stdout / a return value back to Codex. Put the summary there.

### 3. Template — always start from this shape

```csharp
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using System.Linq;
using System.Text;

// --- Change these to match the task ---
var category = BuiltInCategory.OST_Walls;
// ----------------------------------------

var sb = new StringBuilder();
var count = 0;

using (var t = new Transaction(doc, "Custom MCP operation")) {
    t.Start();
    try {
        var elements = new FilteredElementCollector(doc)
            .OfCategory(category)
            .WhereElementIsNotElementType()
            .ToList();

        foreach (var e in elements) {
            // Your logic here
            count++;
        }

        t.Commit();
    } catch (System.Exception ex) {
        t.RollBack();
        return $"Failed: {ex.Message}";
    }
}

return $"Processed {count} elements.";
```

Adapt the category, the loop body, and the return message to the user's request.

### 4. Show the code before running

Always show the user the C# you're about to run in a fenced code block, plus a one-line summary of what it does. Then ask:

> Run this in Revit?

Only on explicit yes, call `send_code_to_revit`. Do not auto-run code — this is a destructive escape hatch, and the user should see what's executing. This applies even in auto mode.

### 5. Handle errors

The Revit API throws rich exceptions. When `send_code_to_revit` returns an error:

- `InvalidObjectException` → your collector returned elements that were deleted or disposed. Refresh the query.
- `Attempt to modify document outside of a transaction` → you forgot the `using (var t = ...)` wrapper.
- `AccessViolationException` → you dereferenced a null `Element`. Guard with `?.` or `if (e == null) continue;`.
- Permission errors (write to worksets the user doesn't own) → nothing the code can do; tell the user which worksets need to be checked out.

Interpret the error, show the user the fix, and offer to re-run.

### 6. Keep scripts idempotent when you can

If the script adds a parameter value, make it check whether the value is already correct and skip — that way re-running doesn't bloat the undo stack. Log skips in the return message.

## Guardrails

- **Never run code without explicit user confirmation.** Even in auto mode. This tool is a full scripting environment in the user's production CAD software.
- **Never pull in external code** via package install or HTTP in a script. Revit's executor does not need or want network I/O.
- **Avoid infinite loops or unbounded recursion.** Add a max-iteration safety check on any `while` loop.
- **Transactions must close.** If the script can throw, wrap in try/catch with rollback.
- **Don't write to the file system from inside Revit** unless the user explicitly wants an export. Writes should go through the user, not the addin.
- **Show, then ask, then run.** Never the other order.

## Example conversations

> **User**: "Set the 'Comments' parameter of every door to include its host room's number."
>
> **You**: write a script that collects doors, finds the room the door's location is in, concatenates the room number, sets the parameter. Show it. Ask. Run.

> **User**: "Rename all levels to 'L-01', 'L-02', etc., in order of elevation."
>
> **You**: collect levels, sort by `Elevation`, iterate with index, `level.Name = $"L-{(i+1):00}"`. Transaction-wrapped. Show, ask, run.
