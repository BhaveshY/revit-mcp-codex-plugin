# Set Up Weekly Revit Learning

Use this flow only after the user directly requests learning setup, including by
selecting the plugin's setup starter. Codex plugins cannot activate scheduled
tasks during package installation, so this skill owns the supported one-click
desktop setup.

Read `../plugin-author-config/automation-config.md` for the canonical name,
cadence, and thin run instructions.

## Idempotent setup

1. Confirm native Windows 11 and find the existing Revit MCP Next launcher by
   the resolution order in the parent skill. Do not reinstall a working runtime.
2. Discover the Codex desktop automation and task tools. Search existing tasks
   for the exact title `Revit Plugin Weekly Improvement`; reuse only one clearly
   matching pinned task. Do not reuse the current task or an unrelated project.
3. If no matching task exists, create a dedicated projectless task named
   `revit-plugin-learning` with title `Revit Plugin Weekly Improvement`, model
   `gpt-5.6-sol`, and medium reasoning, then pin it. This per-user task is the
   writable maintenance workspace and avoids machine-specific project IDs.
4. Create or update automation `revit-plugin-improvement-review` as an active
   heartbeat targeting exactly that pinned task. Convert Monday at 11:00 AM
   local time to the narrowest supported weekly schedule and use the exact
   Instructions from the config as its prompt. Never write an automation TOML
   file directly.
5. Read the automation back with the app tool. Confirm its target task, prompt,
   cadence, and active status. Repair once if they differ; do not create a
   duplicate.
6. Send one kickoff to the pinned task after successful readback. Tell it to
   clone `https://github.com/BhaveshY/revit-mcp-codex-plugin` into its workspace
   if absent, preserve any dirty checkout, validate the plugin and tests, check
   Git/GitHub draft-PR access, and report readiness. The kickoff prepares the
   workspace but does not mine task history or edit skills.
7. Report setup complete only after automation readback and kickoff succeed.
   If GitHub write access is absent, the weekly review may still diagnose and
   test locally, but it must report that it cannot publish a draft PR.

Do not delete or unpin possible duplicates without explicit approval. Do not
store raw chats in setup metadata. The scheduled maintenance skill remains the
sole owner of history review, evidence gates, skill deduplication, and patches.
