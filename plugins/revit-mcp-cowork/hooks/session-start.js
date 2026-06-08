#!/usr/bin/env node
/**
 * SessionStart hook — injects Revit MCP tool-safety rules into every session.
 *
 * This ensures the safety discipline applies to ALL Revit tool use, not just
 * when one of the configured skills is invoked. Even ad-hoc queries, direct
 * tool calls, or custom user prompts pick up the rules.
 *
 * Fail-open: if anything goes wrong, print an empty object so the session
 * starts normally rather than erroring.
 */

"use strict";

const context = `# Revit MCP Tool Safety — Active for Every Revit Tool Call

This plugin wraps the upstream \`mcp-servers-for-revit\` MCP server, which has
several source-verified bugs that produce wrong answers unless mitigated.
These rules apply to EVERY Revit MCP tool call in this session, regardless
of whether a configured skill is handling the request.

## The single most important rule
Never quote a returned-array length as a count. Most list tools silently
truncate. Counts come from \`analyze_model_statistics\` or
\`send_code_to_revit\` with \`FilteredElementCollector.GetElementCount()\`.

## Silent caps (auto-enforced by PreToolUse hook)
The hook will DENY calls to these tools if they omit the safe explicit limit.
Retry the call with the limit raised:

| Tool | Required parameter |
|---|---|
| \`ai_element_filter\` | \`maxElements: 100000\` |
| \`get_current_view_elements\` | \`limit: 100000\` |
| \`get_selected_elements\` | \`limit: 100000\` |
| \`get_available_family_types\` | \`limit: 100000\` |

## Blocked tools
\`say_hello\` is blocked — it shows a blocking TaskDialog in Revit that wedges
the UI. For a health check, use \`send_code_to_revit\` with a one-line ping
snippet instead.

## Unit inconsistencies — convert on ingestion
The server does NOT normalize units. Convert before displaying to users:

- \`ai_element_filter\` — mm (already converted)
- \`get_material_quantities\` — **ft² / ft³** (multiply by 0.092903 / 0.0283168)
- \`export_room_data\` — **ft / ft² / ft³**
- \`analyze_model_statistics.Levels[].Elevation\` — **feet** (×304.8 for mm)
- \`get_current_view_elements\` location fields — **feet**
- \`tag_all_walls\` locations — **feet**; \`tag_all_rooms\` locations — **mm**

Always state units in every user-facing report.

## Bilingual errors
Scan every Revit tool response for Chinese error prefixes. The PostToolUse
hook surfaces these automatically. Treat as errors, not data:
\`操作超时\` (timeout), \`失败\` (failed), \`错误\` (error), \`超时\` (timeout),
\`未找到\` (not found), \`文档未激活\` (doc not active).

## Silent side-effects to watch
- \`create_*\` tools silently substitute the first available family if \`typeId\`
  missing. Verify type match after every placement.
- \`baseLevel\` on create tools is a HEIGHT, not a level ID — snaps to nearest.
  Read real level elevations first.
- \`tag_all_rooms\`, \`operate_element SelectionBox/SetColor\` silently switch
  the active view. Capture the view name before and compare after.
- \`delete_element\` cascades — \`DeletedCount\` can exceed input length.
  Snapshot \`analyze_model_statistics\` before and after.
- \`create_structural_framing_system\` silently auto-creates a level at 4 m
  spacing if \`levelName\` matches \`Level N\` pattern and doesn't exist.

## Citation discipline
Every factual claim about quantities MUST cite its source tool, e.g.:
"142 doors (source: analyze_model_statistics)." Never bare numbers.

## Full details
The \`revit-tool-safety\` skill has the complete 17-rule contract and C#
snippets for verification. The hooks enforce the non-negotiable subset.`;

try {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: context
    }
  }) + "\n");
} catch (_) {
  // Fail open
  process.stdout.write("{}\n");
}
