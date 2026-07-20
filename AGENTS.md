# Agent Instructions

This repository packages Codex skills and an MCP launcher for
`BhaveshY/revit-mcp-next`. Keep it a lightweight companion; do not vendor the
Revit broker or add-in.

Runtime support is strictly native Windows 11 with local Autodesk Revit 2024.
Do not add macOS, Linux, WSL, container, Wine, or remote-host fallbacks.

- Treat the live Revit MCP Next schemas and discovery resources as authoritative.
- Preserve the stable plugin ID and marketplace path unless a migration is planned.
- Keep repository install/build work out of normal MCP startup and hand off
  directly to the installed Windows launcher; setup remains explicit.
- Keep writes on the preview/apply path and preserve document/generation guards.
- Never expose `config\auth.env` or automate Revit security prompts without explicit approval.
- Validate every skill and the plugin manifest before handoff.
