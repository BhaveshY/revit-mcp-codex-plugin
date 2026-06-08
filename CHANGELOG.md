# Changelog

All notable changes to the `revit-mcp-cowork` plugin. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [0.6.0] — 2026-04-22

### Added — hook-enforced tool safety (applies to EVERY Revit tool call)

Skills only fire when Claude chooses them. If a user writes an ad-hoc query that doesn't match a skill trigger, the tool-safety rules in v0.5.0 would not apply. Hooks run at the transport layer and enforce safety regardless of whether any skill is active.

- **`hooks/hooks.json`** — configuration for SessionStart, PreToolUse, and PostToolUse hooks matching `mcp__*revit*__*` tool names.
- **`hooks/session-start.js`** — injects the tool-safety summary into every Revit session as `additionalContext`. Silent caps, unit inconsistencies, blocked tools, bilingual errors, citation discipline. Always in context whenever the plugin is active.
- **`hooks/pre-tool.js`** — intercepts every Revit MCP tool call before it runs:
  - **Blocks** `ai_element_filter` / `get_current_view_elements` / `get_selected_elements` / `get_available_family_types` if they omit the safe explicit limit. The tool call is denied with a retry instruction containing the exact parameter to add. Claude retries with `maxElements: 100000` (or `limit: 100000`) and the call succeeds. Silent truncation is now impossible.
  - **Blocks** `say_hello` outright — it shows a blocking modal in Revit that wedges the UI. Suggests the `send_code_to_revit` health-ping snippet instead.
  - **Warns** on `delete_element` (cascade risk — suggests pre/post `analyze_model_statistics` snapshots).
  - **Warns** on `send_code_to_revit` (transaction mode + 60s timeout reminder).
- **`hooks/post-tool.js`** — scans every Revit MCP tool response for red flags and surfaces them to Claude:
  - Chinese error prefixes (`操作超时`, `失败`, `错误`, `获取元素信息时出错`, etc.) — translates to English and marks as error, not data.
  - Known silent-cap response lengths (`ai_element_filter` returning exactly 50 elements, `get_current_view_elements` returning exactly 100) — flags as "almost certainly truncated" and instructs a retry.
  - `Success: false` responses — flags as failure, prevents silent continuation.
- **`plugin.json`** — declares the hooks path explicitly.

### Impact

The v0.5.0 skill-level discipline is now backed by the harness itself:

- Even if the user writes a prompt that doesn't trigger any configured skill, the PreToolUse hook enforces safe parameters on capped tools.
- Even if Claude's attention drifts mid-session, the PostToolUse hook catches anomalies before they reach the user.
- Even ad-hoc C# scripts benefit from transaction + timeout reminders.

Combined with v0.5.0's skill rules, the plugin now has **two independent layers** protecting against wrong answers: the skills provide guidance + templates, and the hooks provide deterministic enforcement.

### Fail-open discipline

All hooks fail open. If a script errors, the tool call proceeds as if the hook didn't run. A broken safety layer is worse than no safety layer — but in practice the hooks have been smoke-tested against truncation, blocked tools, Chinese errors, and success responses.

### Compatibility

- Node.js 18+ (already required for the MCP server — no new dependency).
- All hook scripts are cross-platform (macOS, Windows, Linux) via Node.
- Plugin-local relative paths are resolved from the installed plugin root, so the docs and hooks work regardless of install location.

## [0.5.0] — 2026-04-21

### Added — enterprise-grade accuracy

Source-level audit of `mcp-servers-for-revit` surfaced 20+ hidden caps, silent fallbacks, unit inconsistencies, and side-effects that produce wrong answers in naive use. This release bakes the full mitigation set into the plugin.

- **New skill: `revit-tool-safety`** — universal discipline invoked before any Revit MCP tool call. Enforces 17 rules:
  1. Always pass explicit high limits on listing tools (bypass 50/100 silent caps).
  2. Counts come from `analyze_model_statistics` or `send_code_to_revit`, never from filter result length.
  3. Round-number results (exactly 50, 100) trigger re-query — the `ai_element_filter` "X of X" message is buggy after `Take()`.
  4. Cross-verify every user-facing count via two independent tools.
  5. Normalize units on ingestion (the server mixes mm and ft across tools).
  6. Verify family type after every `create_*` call (silent fallback to first available symbol).
  7. `baseLevel` is a height, not a level ID — read real elevations first.
  8. Structural framing system auto-creates levels on `Level N` pattern — pre-verify.
  9. `delete_element` cascades — snapshot counts before/after.
  10. Silent view mutations on `tag_all_rooms`, `operate_element SelectionBox/SetColor` — capture and notify.
  11. Health check uses `send_code_to_revit`, never `say_hello` (blocking modal).
  12. Translate Chinese error strings to English.
  13. Retry transport timeouts exactly once.
  14. Phantom tools (0-byte files) ignored.
  15. `ai_element_filter` bounding-box schema is broken — filter plugin-side.
  16. Validate input to `delete_element` / `operate_element` — bad input triggers blocking dialogs.
  17. `store_project_data` upsert is name-keyed — include a unique suffix.
- **`references/tool-reference.md`** — every tool's real defaults, limits, units, silent behaviors, and workarounds. Source-verified against the upstream repo.
- **`references/verification-patterns.md`** — ready-to-run C# snippets for accurate counting, cross-verification, health checks, cascade accounting, type-match verification, room-enclosure verification, and view-switch detection.
- **`references/canonical-queries.md`** — full-enumeration templates that bypass caps (uncapped replacements for `ai_element_filter`, `get_current_view_elements`, `get_selected_elements`, `get_available_family_types`) plus a user-term → `BuiltInCategory` map covering 26 common categories.
- **Updated every existing skill** to reference `revit-tool-safety` explicitly and apply the rules it requires. In particular:
  - `setup-revit` — health check now uses a `send_code_to_revit` snippet instead of the blocking `say_hello`.
  - `model-audit` — mandates `analyze_model_statistics` for counts; forbids `ai_element_filter.length` as a count source.
  - `find-and-modify` — deletes are bracketed by before/after snapshots; cascade deletions reported separately.
  - `quick-model` — verifies type match after every `create_*`; pulls exact level elevations before placement.
  - `scaffold-project` — checks for level collisions via `AlreadyExisted`; passes explicit grid extents.
  - `structural-framing` — pre-verifies `levelName` exists before creation (prevents silent auto-level).
  - `revit-excel-sync`, `revit-mirror` — pass `maxElements: 100000` on every filter; cross-verify expected update counts.

### Impact

Reported numbers are now trustworthy to the same standard as a human opening Revit's project browser and counting. The previously-reported "50 doors when there are 142" failure mode is eliminated. Enterprise users can rely on plugin output for construction documents, schedules, and coordination decisions.

## [0.4.1] — 2026-04-21

### Added
- **`.codex-plugin/marketplace.json`** — the repo now works as a Claude plugin marketplace. Users can install via `/plugin marketplace add BhaveshY/revit-mcp-cowork` followed by `/plugin install revit-mcp-cowork@revit-mcp-cowork`.
- README updated with both install paths (marketplace + `.plugin` file).

### Fixed
- "Marketplace manifest not found at `.codex-plugin/marketplace.json`" when adding the repo as a marketplace.

## [0.4.0] — 2026-04-21

### Added
- **Freshness guards in `revit-mirror`** — four non-optional safety patterns applied on every Excel write:
  1. Re-read fresh from disk (no reuse of conversation-cached data)
  2. Excel lock-file detection (`~$<filename>.xlsx`)
  3. Mtime / TOCTOU check before write
  4. Atomic write via temp-file + rename (same directory)
- **Backup-on-bulk**: automatic timestamped backups before any mirror run that touches >50 rows or >3 categories.
- **`references/safety-patterns.md`** in `revit-mirror` with code templates for each guard, platform-specific notes (NTFS / SMB / APFS / NFS), and step-by-step procedures.
- **Connection health check** in `setup-revit` — implicit two-call verification (`say_hello` + `get_current_view_info`) at the start of every session and before destructive operations. Halts early on common failure modes (Revit closed, no document, bridge stopped).
- **Top-level `TROUBLESHOOTING.md`** covering bridge issues, mirror failures, install problems, and performance tuning.
- `LICENSE` (MIT), `.gitignore`, this `CHANGELOG.md`.

### Changed
- `revit-mirror` SKILL.md now requires the freshness guards in Phase 3 — they are not optional. The skill halts if any guard fails and never silently proceeds past a stale-data condition.
- `revit-mirror` report format explicitly names the backup path (when created) and the guards that ran.

### Notes
- No breaking changes to skill triggering phrases or MCP configuration.
- Existing pinned sheets remain valid; no re-pinning required.

## [0.3.0] — 2026-04-21

### Added
- **`revit-mirror` skill** — first-class orchestrator for single-prompt workflows that modify Revit *and* update an Excel tracker in one turn.
- Pinned-sheet support: `pin <path> as the doors tracker` persists the target so subsequent prompts mirror automatically.
- **`references/network-storage.md`** covering three patterns for NAS-hosted xlsx files (QNAP / Synology / SMB): mount as drive, local staging copy, or File Station HTTP API.

### Changed
- README rewritten to introduce the eleven skills (was ten) and example Excel prompts.

## [0.2.0] — 2026-04-21

### Added
- **`revit-excel-sync` skill** — bidirectional Revit ↔ Excel sync with three modes: PULL (Revit → xlsx), PUSH (xlsx → Revit, confirmation-gated), DIFF (compare without changes).
- **`references/parameter-mappings.md`** — column header ↔ Revit parameter ↔ `BuiltInParameter` enum for Doors, Windows, Walls, Rooms, Floors, Columns, Structural Framing, plus shared-parameter fallback and unit conversions.
- **`references/push-csharp-template.md`** — transactioned C# template for `send_code_to_revit` with per-row error isolation, unit conversion, and type-parameter safety.

### Changed
- Plugin keywords add `excel`, `xlsx`, `boq`.

## [0.1.0] — 2026-04-21

### Added
- Initial release.
- Nine skills covering the BIM lifecycle: `setup-revit`, `scaffold-project`, `quick-model`, `model-audit`, `document-model`, `generate-schedule`, `find-and-modify`, `structural-framing`, `revit-code-runner`.
- `.mcp.json` configured for Revit MCP server via `cmd /c npx -y mcp-server-for-revit` (Windows, Revit 2024).
- `plugin.json` manifest and `README.md`.
