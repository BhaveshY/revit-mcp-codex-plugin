#!/usr/bin/env node
/**
 * PreToolUse hook — intercepts Revit MCP tool calls and enforces safety.
 *
 * For the 4 silently-capped tools, DENIES calls that omit the safe limit and
 * returns an instructive message that tells Claude to retry with the safe
 * parameter value.
 *
 * Blocks `say_hello` outright (it shows a blocking modal in Revit).
 *
 * For `delete_element`, warns (via additionalContext) that cascade counts
 * should be tracked.
 *
 * Fail-open: on any parse / IO error, allow the call. Safety > correctness
 * should never equal broken plugin.
 */

"use strict";

const TOOL_CAPS = {
  ai_element_filter:          { key: "maxElements", safeMin: 10000, safeValue: 100000 },
  get_current_view_elements:  { key: "limit",       safeMin: 10000, safeValue: 100000 },
  get_selected_elements:      { key: "limit",       safeMin: 10000, safeValue: 100000 },
  get_available_family_types: { key: "limit",       safeMin: 10000, safeValue: 100000 }
};

const BLOCKED_TOOLS = {
  say_hello: "say_hello shows a blocking modal TaskDialog in Revit that halts the Revit UI until a human clicks OK. Never call it from automation. For a health check, call send_code_to_revit with this snippet:\n\ncsharp\nreturn new { ok = true, title = document?.Title ?? \"(no document)\", view = document?.ActiveView?.Name ?? \"(no view)\" };\n\nSee skills/revit-tool-safety/references/verification-patterns.md."
};

// Try to extract the short Revit tool name (last segment) from a possibly
// namespaced name like mcp__revit__ai_element_filter or
// mcp__plugin_revit-mcp-cowork_revit__ai_element_filter.
function shortRevitTool(toolName) {
  if (!toolName || typeof toolName !== "string") return null;
  // Must look like an MCP Revit tool
  if (!/revit/i.test(toolName)) return null;
  // Split on "__" (MCP namespace separator) and take the last segment
  const parts = toolName.split("__");
  if (parts.length < 2) return null;
  return parts[parts.length - 1];
}

let buf = "";
process.stdin.on("data", d => { buf += d; });
process.stdin.on("end", () => {
  try {
    const payload = JSON.parse(buf || "{}");
    const toolName = payload.tool_name || payload.toolName || "";
    const toolInput = payload.tool_input || payload.toolInput || {};

    const short = shortRevitTool(toolName);
    if (!short) {
      return allow();
    }

    // Blocked tools
    if (BLOCKED_TOOLS[short]) {
      return deny(BLOCKED_TOOLS[short]);
    }

    // Capped tools — enforce safe limits
    const cap = TOOL_CAPS[short];
    if (cap) {
      const v = toolInput[cap.key];
      const numeric = typeof v === "number" ? v : (v !== undefined && v !== null ? Number(v) : NaN);
      if (!(numeric >= cap.safeMin)) {
        return deny(
          `Safety guard (revit-mcp-cowork): \`${short}\` silently caps results at a low default (50 or 100), and the server does NOT report a true total — truncation is invisible.\n\n` +
          `Retry this call with \`"${cap.key}": ${cap.safeValue}\` added to the tool input. Do not interpret the previous response if it was returned; it may be truncated.\n\n` +
          `For counts, use analyze_model_statistics or send_code_to_revit instead (see skills/revit-tool-safety/SKILL.md rules 1 & 2).`
        );
      }
    }

    // Warn on delete_element — cascade risk
    if (short === "delete_element") {
      return allowWithContext(
        `Safety reminder: delete_element cascades (tags, hosted families, joined walls). Revit's DeletedCount typically exceeds the input list length. To report cascades accurately to the user, call analyze_model_statistics before and after this delete. See skills/revit-tool-safety/SKILL.md Rule 9.`
      );
    }

    // Warn on send_code_to_revit — reminder about transaction & timeouts
    if (short === "send_code_to_revit") {
      return allowWithContext(
        `Reminder: send_code_to_revit has a 60s wall-clock timeout and auto-wraps code in a Revit Transaction (unless transactionMode: "none" is set; not available on npm 1.0.0). For pure queries, use FilteredElementCollector.GetElementCount() patterns from skills/revit-tool-safety/references/verification-patterns.md. For mutations, wrap explicit transactions with try/catch + rollback.`
      );
    }

    return allow();
  } catch (e) {
    // Fail open — never block the tool due to hook errors
    return allow();
  }
});

function allow() {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow"
    }
  }) + "\n");
}

function allowWithContext(ctx) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow",
      additionalContext: ctx
    }
  }) + "\n");
}

function deny(reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: reason
    }
  }) + "\n");
}
