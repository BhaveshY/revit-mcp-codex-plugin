# Working With Excel Files On A NAS

Many BIM offices keep project trackers on a NAS: QNAP, Synology, Windows Server shares, TrueNAS, and similar systems. Codex can only read and write files it can see as local paths. When the xlsx lives on a NAS, use one of these three patterns and keep it consistent per project.

## Pattern A - Mount The Share As A Local Drive

This is the simplest and fastest path. Every modern NAS speaks SMB; mounting makes the share look like any folder on the Codex host.

### On Windows

Use this when Revit and Codex are on the same Windows machine.

1. File Explorer -> **This PC** -> **Map network drive**.
2. Drive letter: `Z:` or any free letter.
3. Folder: `\\<qnap-hostname-or-ip>\<share-name>`, for example `\\qnap.local\Projects`.
4. Tick **Reconnect at sign-in** and **Connect using different credentials**.
5. Once mapped, files show at paths like `Z:\ProjectX\trackers\doors.xlsx`. Codex can read and write them with normal file tools.

Command-line equivalent:

```cmd
net use Z: \\qnap.local\Projects /user:<user> <password> /persistent:yes
```

### On macOS

Use this only if Codex is running on Mac for the spreadsheet side.

1. Finder -> **Go** -> **Connect to Server**.
2. Address: `smb://qnap.local/Projects`.
3. Mounted path: `/Volumes/Projects/...`

Command-line equivalent:

```bash
mkdir -p ~/qnap && mount_smbfs //user:password@qnap.local/Projects ~/qnap
```

### After Mounting

- Pin the file with its mounted path: `Z:\ProjectX\trackers\doors.xlsx` on Windows or `/Volumes/Projects/ProjectX/trackers/doors.xlsx` on Mac.
- The `revit-mirror` and `revit-excel-sync` skills will read and write through the mount. No plugin changes are needed.
- Codex's file-access sandbox may prompt the first time it touches a path outside the normal workspace. Grant access if the path is expected.

### Caveats With Live Excel Edits

If someone has the file open in Excel on a different machine, the mount will either refuse the write or create a conflict copy. Coordinate the workflow: either Excel is closed before the mirror runs, or the team uses a platform with real co-authoring. Plain SMB shares do not provide safe workbook co-authoring.

## Pattern B - Local Staging Folder And Manual Sync Back

Use this when the NAS cannot be mounted, VPN or IT policy blocks SMB, Codex sandbox access is restricted, or the team wants a deliberate review step before the canonical NAS copy changes.

### Setup

1. Create a local working directory, for example `C:\RevitMirror\` or `~/revit-mirror/`.
2. Before asking Codex to mirror, copy the current tracker xlsx from the NAS into that directory.
3. Pin the local copy as the mirror target: `C:\RevitMirror\doors.xlsx`.
4. After Codex updates it, copy it back to the NAS manually or via script.

### Optional Automation

Windows `sync.bat`:

```cmd
robocopy "\\qnap.local\Projects\ProjectX\trackers" "C:\RevitMirror" doors.xlsx /Z
```

macOS or Linux `sync.sh`:

```bash
rsync -av /Volumes/Projects/ProjectX/trackers/doors.xlsx ~/revit-mirror/
# ... Codex works on the file ...
rsync -av ~/revit-mirror/doors.xlsx /Volumes/Projects/ProjectX/trackers/
```

Trade-off: manual step, but explicit. You always know when the team's copy changed.

## Pattern C - NAS HTTP API Through MCP

QNAP exposes a REST API for file operations. Synology File Station and TrueNAS have similar APIs. Wrapping that API in a small MCP server gives Codex direct access without mounting. This is more infrastructure than most teams need.

Rough shape:

1. Authenticate against the NAS API to get a session token.
2. Expose download, upload, and list operations through a small stdio MCP server.
3. Add that MCP server to `.mcp.json` alongside the Revit server.

Pros: no mount needed, works across machines, supports fine-grained permissions.
Cons: bespoke code, auth tokens to manage, one more moving part.

Only use this if Pattern A is blocked and Pattern B's manual step is unacceptable.

## Which Pattern To Choose

| Situation | Use |
|---|---|
| Codex is on the same machine as Revit and QNAP is reachable via SMB | Pattern A |
| Codex runs on a different machine than Revit, both on the same LAN | Pattern A on each host |
| IT blocks SMB mounts but the NAS HTTPS interface is reachable | Pattern C |
| The team wants a review step before the NAS is modified | Pattern B |
| First-time setup or testing | Pattern B |

## Before Running A Mirror On A NAS Path

1. **Verify the path is reachable.** Use `dir Z:\ProjectX\trackers` on Windows or `ls /Volumes/Projects/...` on Mac. If this fails, remount before continuing.
2. **Ask who has the file open.** If someone is editing the tracker live, the write will fail or produce a conflict copy.
3. **Back up before bulk operations.** For pushes over 50 rows, copy the xlsx to `<name>-backup-<date>.xlsx` first.
4. **Expect slower I/O.** SMB over Wi-Fi is much slower than local SSD. Large xlsx reads may take a few seconds.
