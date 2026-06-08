# Safety Patterns for Excel Mirror Writes

Code templates and step-by-step procedures for the four freshness guards required in `revit-mirror` Phase 3. Apply these in order, every time.

These patterns apply regardless of whether the xlsx is on a local disk, a mounted NAS (QNAP / Synology / SMB share), or a cloud-sync folder — the failure modes differ but the guards catch them uniformly.

## Guard 1 — Re-read fresh

**Purpose**: avoid operating on a copy of the xlsx that Claude read earlier in the conversation. Conversation memory is not a file cache.

**Procedure**:

1. At the very start of Phase 3, discard any in-memory representation of the xlsx from earlier turns.
2. Invoke `anthropic-skills:xlsx` with a fresh read of the target path.
3. Use the just-read data as the baseline for diffing.

**Anti-patterns**:

- ❌ "Based on what we saw earlier, row 14 has width 900" — no. Re-read.
- ❌ Reusing a parsed table from the pull phase — no. Re-read.
- ✅ Every mirror starts with a fresh disk read of the xlsx.

## Guard 2 — Lock-file detection

**Purpose**: refuse to write when Excel has the file open with an exclusive lock. Excel creates a sentinel lock file in the same directory that starts with `~$`.

**Procedure** (pseudocode — adapt to the environment):

```
dir = os.path.dirname(xlsx_path)
name = os.path.basename(xlsx_path)
lock_name = "~$" + name
lock_path = os.path.join(dir, lock_name)

if os.path.exists(lock_path):
    abort("Excel lock file present at " + lock_path + 
          ". Close the file in Excel, then retry.")
```

**Edge cases**:

- Some Excel crashes leave an orphan `~$` file behind. If the user insists Excel is closed, check the file's mtime — if older than an hour, it's probably orphan. Suggest the user delete it manually and retry.
- macOS `.DS_Store` files are unrelated — ignore.
- OneDrive / SharePoint sync folders have their own lock semantics. This guard addresses Excel's desktop lock only.

**If multiple users collaborate via SharePoint / OneDrive Business**: co-authoring bypasses the classic lock file and uses server-side merging. This mirror pattern does not support live co-auth; advise the user to work on a non-co-authored copy for Revit-sync purposes.

## Guard 3 — Mtime / ETag check (TOCTOU guard)

**Purpose**: catch the case where another process or user saved the file between Claude's read and Claude's write (TOCTOU — time of check to time of use).

**Procedure**:

```
# At start of Phase 3 read
stat_before = os.stat(xlsx_path)
mtime_before = stat_before.st_mtime

# ... do the diff computation ...

# Immediately before write
stat_now = os.stat(xlsx_path)
if abs(stat_now.st_mtime - mtime_before) > 0.001:
    # File was modified since we read it
    prompt_user(
        f"The sheet was modified at {stat_now.st_mtime} "
        f"(we read at {mtime_before}). "
        f"Re-read and retry, or overwrite anyway?"
    )
    # Default: abort. Only overwrite on explicit yes.
```

**Tolerance**: SMB mtime resolution is sometimes 1–2 seconds. If the before/after delta is tiny (<2s) and no other signal (like a lock file appearing) suggests concurrent access, a warning is enough. Otherwise abort.

**Re-read retry**: if the user says "re-read and retry," discard the computed diff, re-run Guard 1, recompute the diff against the new baseline, and re-apply. Loop at most twice — if the file is being actively saved by someone else, back off and ask the user to coordinate.

## Guard 4 — Atomic write via temp + rename

**Purpose**: if the write is interrupted (network drop, process kill, disk full), the original file is untouched. Either the whole new file replaces the old, or nothing happens.

**Procedure**:

```
import os, tempfile

dir = os.path.dirname(xlsx_path)
fd, tmp_path = tempfile.mkstemp(
    dir=dir,
    prefix=os.path.basename(xlsx_path) + ".tmp.",
    suffix=".xlsx"
)
os.close(fd)

try:
    write_xlsx(tmp_path, new_data)         # full write to temp
    os.replace(tmp_path, xlsx_path)         # atomic rename (same dir)
except Exception:
    # Tmp file may exist — clean up
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    raise
```

**Why same directory**: `os.rename` / `os.replace` is atomic only within a single filesystem / share. Crossing filesystems falls back to copy + delete, which isn't atomic. Always keep the tmp file next to the target.

**SMB specifics**: SMB2/3 supports atomic rename within a share. Older SMB1 or some NAS firmware may not — if the user is on a questionable setup, they'll see a partial-write risk warning in our guard output. Upgrade SMB version or fall back to backup-then-write.

**Permissions**: the rename silently preserves the original file's ACL on Windows / NTFS. On SMB mounts, the temp file inherits the share's default ACL, which should match. Verify on first run.

## Backup-on-bulk

**Purpose**: for large or multi-category mirrors, keep a snapshot the user can fall back to even if all guards pass. Cheap insurance.

**Triggers**: apply when any of these hold:

- More than 50 rows will be modified.
- More than 3 categories (sheets) will be touched.
- The user explicitly asked ("back up first").
- The xlsx is on a NAS (where undo is less accessible than local).

**Procedure**:

```
import shutil, datetime

timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
backup_name = xlsx_path.replace(".xlsx", f".backup.{timestamp}.xlsx")

# Prefer a `backups/` subdir if it exists
backup_dir = os.path.join(os.path.dirname(xlsx_path), "backups")
if os.path.isdir(backup_dir):
    backup_name = os.path.join(backup_dir, os.path.basename(backup_name))

shutil.copy2(xlsx_path, backup_name)  # copy2 preserves mtime/permissions
```

**Reporting**: always include the backup path in the final summary. Example:

> Backup written to `Z:\Projects\X\trackers\backups\doors.backup.2026-04-21T14-30-22.xlsx` before applying 78 cell changes.

**Retention**: the mirror does not delete old backups. That's the user's call. Suggest a monthly sweep in the project's operating conventions.

## Full flow — putting it together

```
# Phase 3 — Mirror to Excel
1. Resolve target path (from pin or prompt).
2. GUARD 1: Re-read fresh. Discard any prior in-memory xlsx data.
3. GUARD 2: Check for ~$<filename>.xlsx lock. If present, abort with friendly message.
4. Compute cell-level diff (Revit current state vs. xlsx rows).
5. If diff is empty: log "no mirror changes needed" and stop.
6. If diff triggers backup-on-bulk: create timestamped backup copy.
7. GUARD 3: Re-stat xlsx. If mtime changed since step 2, prompt to re-read or overwrite.
8. GUARD 4: Write new bytes to <file>.xlsx.tmp.<pid> in the same directory.
9. Flush, close, fsync.
10. Atomic rename tmp -> real path.
11. Report: Revit result + backup path (if any) + rows added/modified/marked-deleted.
```

## When a guard halts the mirror, Revit is already changed

This is a real failure mode. Phase 2 wrote to Revit, then Phase 3 hit a guard and stopped. Tell the user explicitly:

> ⚠ Revit was updated (14 doors). The Excel mirror did NOT complete — the sheet is stale relative to the model.
>
> Options:
>   1. Fix the blocker (close the xlsx in Excel / refresh the NAS mount) and re-run just the mirror half: *"re-mirror the last Revit change to doors.xlsx"*
>   2. Undo the Revit change in Revit (Ctrl-Z) to put both sides back in sync, then retry the original prompt.

Never silently retry. Never pretend the mirror succeeded.

## Platform notes

- **Windows + NTFS**: all four guards work perfectly. `os.replace` is atomic.
- **Windows + SMB to QNAP / Synology**: works; rename is atomic within the share. Slightly higher mtime-tolerance window due to SMB timestamp quantization.
- **macOS + local APFS**: works perfectly.
- **macOS + SMB mount**: works; `.DS_Store` files in the directory are harmless.
- **Linux + NFS**: rename atomicity depends on NFS version (v4 yes, v3 less strict). If the user is on NFS, surface that during setup and prefer Pattern B from network-storage.md.
