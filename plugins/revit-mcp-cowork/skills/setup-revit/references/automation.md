# Set Up Weekly Revit Learning

Use this only after the user directly requests learning setup, including by
selecting the plugin starter. Read
`../plugin-author-config/automation-config.md` for the canonical name, cadence,
and thin run instructions.

1. Confirm native Windows 11 and the existing Revit MCP Next launcher. Do not
   reinstall a working runtime.
2. After hook trust, call a small Revit status tool once so `PLUGIN_DATA` is
   registered. Run the bundled `scripts/manage-revit-learning.ps1` with
   `-Action InitializeLocal`, requesting persistent approval for only that
   manager command. Read back `-Action LocalStatus`.
3. Find one pinned projectless task titled `Revit Plugin Weekly Improvement`.
   Reuse an exact match or create it with model `gpt-5.6-sol` and medium
   reasoning. Never reuse the current task or an unrelated project.
4. Create or update automation `revit-plugin-improvement-review` as an active
   heartbeat targeting that task. Use Monday at 11:00 AM local time and the
   exact Instructions from the config. Never write automation TOML directly.
5. Read the automation back. Confirm its target, prompt, cadence, and active
   status; repair once rather than creating a duplicate.
6. Send one kickoff asking the pinned task to run the manager's `LocalStatus`
   action and report readiness. Do not scan history during setup.

Setup is complete only after the local skill, automation readback, and kickoff
succeed. No checkout, Git, GitHub account, branch, PR, or publishing is part of
this workflow. New Codex tasks detect user-skill updates automatically; if an
update is not visible, restart Codex.
