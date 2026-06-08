#!/usr/bin/env node
/**
 * PostToolUse hook — scans Revit MCP tool responses for known red flags
 * and surfaces them to Codex as additionalContext so they can't be
 * silently used as data.
 *
 * Red flags detected:
 *   - Chinese error prefixes (the upstream server throws in Chinese)
 *   - Suspicious array lengths matching known silent caps (50, 100)
 *   - Empty/null responses from tools that should have returned data
 *   - Missing expected fields
 *
 * Fail-open: on any error, emit empty output.
 */

"use strict";

const CHINESE_ERROR_PATTERNS = [
  { pattern: "操作超时",              meaning: "operation timed out" },
  { pattern: "代码执行超时",           meaning: "code execution timed out" },
  { pattern: "执行超时",              meaning: "execution timed out" },
  { pattern: "超时",                  meaning: "timeout" },
  { pattern: "获取元素信息时出错",     meaning: "error getting element info" },
  { pattern: "获取元素信息操作超时",   meaning: "get element info timed out" },
  { pattern: "未在项目中找到指定元素", meaning: "no matching element found in project" },
  { pattern: "未在项目中找到",         meaning: "not found in project" },
  { pattern: "未找到",                meaning: "not found" },
  { pattern: "执行失败",              meaning: "execution failed" },
  { pattern: "失败",                  meaning: "failed" },
  { pattern: "错误",                  meaning: "error" },
  { pattern: "文档未激活",             meaning: "document not active" },
  { pattern: "没有活动文档",           meaning: "no active document" },
  { pattern: "没有有效的元素可以删除", meaning: "no valid elements to delete" },
  { pattern: "警告：无法找到类型",     meaning: "warning: cannot find type" },
  { pattern: "无法将",                meaning: "cannot convert" },
  { pattern: "未支持的操作类型",       meaning: "unsupported operation type" }
];

// Known silent-cap values per tool — if response length hits exactly one of
// these, it's almost certainly truncated.
const CAP_CHECKS = {
  ai_element_filter:          { path: "Response",  caps: [50] },
  get_current_view_elements:  { path: "Elements",  caps: [100] }
  // get_selected_elements / get_available_family_types don't have a single
  // well-known response array field we can reliably check here; rely on
  // pre-tool hook + skill rules instead.
};

function shortRevitTool(toolName) {
  if (!toolName || typeof toolName !== "string") return null;
  if (!/revit/i.test(toolName)) return null;
  const parts = toolName.split("__");
  return parts.length >= 2 ? parts[parts.length - 1] : null;
}

function getPath(obj, path) {
  if (!obj || typeof obj !== "object") return undefined;
  return obj[path];
}

let buf = "";
process.stdin.on("data", d => { buf += d; });
process.stdin.on("end", () => {
  try {
    const payload = JSON.parse(buf || "{}");
    const toolName = payload.tool_name || payload.toolName || "";
    const response = payload.tool_response || payload.toolResponse || payload.response || {};
    const short = shortRevitTool(toolName);
    if (!short) return empty();

    const warnings = [];
    const responseStr = JSON.stringify(response);

    // 1. Chinese error prefixes
    for (const { pattern, meaning } of CHINESE_ERROR_PATTERNS) {
      if (responseStr.includes(pattern)) {
        warnings.push(
          `⚠ Revit error detected (bilingual): the tool response contains the Chinese string "${pattern}" (≈ "${meaning}"). Treat as a failure, not as data. Stop any workflow that was going to use this response. Surface the error to the user and suggest a retry or different approach.`
        );
        break; // one is enough to signal
      }
    }

    // 2. Silent-cap detection
    const capCheck = CAP_CHECKS[short];
    if (capCheck) {
      const arr = getPath(response, capCheck.path);
      if (Array.isArray(arr) && capCheck.caps.includes(arr.length)) {
        warnings.push(
          `⚠ Response from \`${short}\` has length ${arr.length}, which exactly matches the known silent cap. This is almost certainly TRUNCATED. DO NOT report this length as a total count. Retry with the explicit safe limit (maxElements: 100000 or limit: 100000), or use analyze_model_statistics / send_code_to_revit for a trustworthy count.`
        );
      }
    }

    // 3. Success flag = false should be treated as error
    if (response && response.Success === false) {
      const msg = response.Message || "(no message)";
      warnings.push(
        `⚠ Revit tool \`${short}\` returned Success=false. Message: "${msg}". Do not proceed as if this succeeded.`
      );
    }

    if (warnings.length === 0) return empty();

    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: warnings.join("\n\n")
      }
    }) + "\n");
  } catch (e) {
    return empty();
  }
});

function empty() {
  process.stdout.write("{}\n");
}
