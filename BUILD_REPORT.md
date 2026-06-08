# Build Report

- Source repo: `/opt/data/codex-plugin-build.yZahYB/sources/revit-mcp-cowork`
- Plugin name: `revit-mcp-cowork`
- Validation commands run:
  - `python3 /opt/data/codex-plugin-build.yZahYB/tools/plugin-creator/scripts/validate_plugin.py /opt/data/codex-plugin-build.yZahYB/targets/revit-mcp-codex-plugin/plugins/revit-mcp-cowork`
  - `python3 -m json.tool /opt/data/codex-plugin-build.yZahYB/targets/revit-mcp-codex-plugin/.agents/plugins/marketplace.json`
  - `python3 -m json.tool /opt/data/codex-plugin-build.yZahYB/targets/revit-mcp-codex-plugin/plugins/revit-mcp-cowork/.codex-plugin/plugin.json`
  - `python3 -m json.tool /opt/data/codex-plugin-build.yZahYB/targets/revit-mcp-codex-plugin/plugins/revit-mcp-cowork/.mcp.json`
- Runtime prerequisites:
  - Autodesk Revit 2024 on Windows
  - Node.js 18+ for `npx -y mcp-server-for-revit`
  - The RevitMCP addin installed under `%AppData%\Autodesk\Revit\Addins\2024\`
