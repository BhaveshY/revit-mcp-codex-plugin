# Working with Excel Files on a NAS (QNAP, Synology, TrueNAS, etc.)

Many BIM offices keep project trackers on a NAS — QNAP, Synology, Windows Server shares, etc. Claude can only read/write files it can see as local paths. When the xlsx lives on a NAS, you have three viable patterns. Pick one per project and stick with it.

## Pattern A — Mount the share as a local drive (recommended)

The simplest and fastest. Every modern NAS speaks SMB; mounting makes the share look like any folder on the Cowork host.

### On Windows (where Revit + ideally Cowork live)

1. File Explorer → **This PC** → **Map network drive**.
2. Drive letter: `Z:` (or any free letter).
3. Folder: `\\<qnap-hostname-or-ip>\<share-name>` (e.g. `\\qnap.local\Projects`).
4. Tick **Reconnect at sign-in** and **Connect using different credentials** (enter NAS user/password).
5. Once mapped, files show at paths like `Z:\ProjectX\trackers\doors.xlsx`. Claude can read/write them with normal file tools.

Command-line equivalent:

```cmd
net use Z: \\qnap.local\Projects /user:<user> <password> /persistent:yes
```

### On macOS (if Cowork is on Mac)

1. Finder → **Go** → **Connect to Server** (`⌘K`).
2. Address: `smb://qnap.local/Projects` → **Connect** → enter credentials.
3. Mounted path: `/Volumes/Projects/...`

Command-line equivalent:

```bash
mkdir -p ~/qnap && mount_smbfs //user:password@qnap.local/Projects ~/qnap
```

### After mounting

- Pin the file with its mounted path: `Z:\ProjectX\trackers\doors.xlsx` (Windows) or `/Volumes/Projects/ProjectX/trackers/doors.xlsx` (Mac).
- The `revit-mirror` skill and `revit-excel-sync` skill will read/write through the mount. No plugin changes needed.
- **Caveat**: Cowork's file-access sandbox may prompt the first time it touches a path outside your home folder. Grant access and it remembers.

### Caveats with live Excel edits

If someone has the file open in Excel on a different machine, the mount will either refuse the write (file-locked) or create a "Copy of" backup. Coordinate: either Excel is closed before the mirror runs, or the team uses Excel's co-authoring (only available on OneDrive/SharePoint, not plain SMB).

## Pattern B — Local staging folder + manual sync back

Use this when the NAS can't be mounted (restrictive IT policy, VPN required, Cowork sandbox blocks it) or when you want a deliberate step between "Claude touched the file" and "the team's canonical copy changes."

### Setup

1. Create a local working directory, e.g. `C:\RevitMirror\` or `~/revit-mirror/`.
2. Before asking Claude to mirror, **copy the current tracker xlsx from the NAS into that directory** manually or via script.
3. Pin the local copy as the mirror target: `C:\RevitMirror\doors.xlsx`.
4. After Claude updates it, **copy it back to the NAS** manually or via script.

### Optional automation

A one-line scheduled task or manual batch:

**Windows** (`sync.bat`):

```cmd
robocopy "\\qnap.local\Projects\ProjectX\trackers" "C:\RevitMirror" doors.xlsx /Z
```

Run it before and after your Claude session.

**macOS / Linux** (`sync.sh`):

```bash
rsync -av /Volumes/Projects/ProjectX/trackers/doors.xlsx ~/revit-mirror/
# ... Claude works on the file ...
rsync -av ~/revit-mirror/doors.xlsx /Volumes/Projects/ProjectX/trackers/
```

Trade-off: manual step, but explicit. You always know when the team's copy changed.

## Pattern C — QNAP File Station HTTP API (advanced)

QNAP exposes a REST API for file ops. Same for Synology (File Station API) and TrueNAS. Wrapping it in an MCP server gives Claude direct access without mounting. This is more infrastructure than most teams need.

### Rough shape

1. Authenticate against `https://<qnap>/cgi-bin/authLogin.cgi` to get a session token.
2. Upload / download / list via `/cgi-bin/filemanager/utilRequest.cgi`.
3. Wrap in a small stdio MCP server exposing `get_xlsx`, `put_xlsx` tools.
4. Add to `.mcp.json` alongside the Revit server.

Pros: no mount needed, works across machines, supports fine-grained permissions.
Cons: bespoke code, auth tokens to manage, one more moving part.

Only recommended if Pattern A is blocked **and** Pattern B's manual step is unacceptable.

## Which pattern to choose

| Situation | Use |
|---|---|
| Cowork is on the same machine as Revit, QNAP reachable via SMB | Pattern A |
| Cowork runs on a different machine than Revit, both on the same LAN | Pattern A on each host |
| IT blocks SMB mounts but you can reach the NAS HTTPS interface | Pattern C |
| You want a review/approval step before NAS is modified | Pattern B |
| First-time setup, just trying things | Pattern B (lowest risk) |

## What to tell the user when the mirror path is on a NAS

Before running a mirror:

1. **Verify the path is reachable.** `ls Z:\ProjectX\trackers` (Windows) or `ls /Volumes/Projects/...` (Mac). If this fails, the mount dropped — remount before continuing.
2. **Ask who has the file open.** If someone is editing the tracker live, the write will fail or produce a conflict copy.
3. **Back up before bulk operations.** For pushes >50 rows, copy the xlsx to `<name>-backup-<date>.xlsx` first. Trivial to undo if needed.
4. **Expect slower I/O.** SMB over Wi-Fi is 10×+ slower than local SSD. Large xlsx reads may take a few seconds.
