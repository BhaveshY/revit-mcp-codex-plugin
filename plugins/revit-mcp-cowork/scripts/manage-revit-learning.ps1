param(
    [ValidateSet('Status', 'Enable', 'Disable', 'Delete', 'Export', 'InitializeLocal', 'ApplyLocal', 'CompleteRun', 'RollbackLocal', 'LocalStatus')]
    [string]$Action = 'Status',
    [string]$ExportPath,
    [string]$CandidatePath,
    [string]$WatermarkUtc
)

$ErrorActionPreference = 'Stop'
$locator = Join-Path $env:LOCALAPPDATA 'RevitMcpNext\CodexLearning\plugin-data-location.json'
if (-not (Test-Path -LiteralPath $locator)) {
    throw 'No plugin data location exists yet. Trust the plugin hook and run one Revit MCP tool first.'
}
$pluginData = (Get-Content -LiteralPath $locator -Raw | ConvertFrom-Json).plugin_data
if ([string]::IsNullOrWhiteSpace($pluginData)) { throw 'The plugin data locator is invalid.' }
$pluginData = [IO.Path]::GetFullPath($pluginData)
$evidenceRoot = Join-Path $pluginData 'learning-evidence'
$disabled = Join-Path $evidenceRoot 'disabled'
$localRoot = Join-Path $pluginData 'local-learning'
$statePath = Join-Path $localRoot 'state.json'
$checkpointPath = Join-Path $localRoot 'review-checkpoint.json'
$generationsRoot = Join-Path $localRoot 'generations'
$journalPath = Join-Path $localRoot 'promotion-journal.json'
$userProfilePath = if (-not [string]::IsNullOrWhiteSpace($env:REVIT_MCP_LEARNING_USER_HOME)) {
    $env:REVIT_MCP_LEARNING_USER_HOME
} else {
    [Environment]::GetFolderPath('UserProfile')
}
if ([string]::IsNullOrWhiteSpace($userProfilePath)) { throw 'The Windows user profile could not be resolved.' }
$skillParent = [IO.Path]::GetFullPath((Join-Path $userProfilePath '.agents\skills'))
$activeSkill = Join-Path $skillParent 'revit-mcp-local-guidance'
$maxRules = 12
$maxSkillBytes = 8192
$maxRuleChars = 300
$script:stateNeedsMigration = $false

function Write-JsonAtomic([string]$Path, [object]$Value) {
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temporary = "$Path.tmp-$([guid]::NewGuid().ToString('N'))"
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Assert-ChildPath([string]$Parent, [string]$Child) {
    $resolvedParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    $resolvedChild = [IO.Path]::GetFullPath($Child)
    if (-not $resolvedChild.StartsWith($resolvedParent, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe path outside the intended root: $resolvedChild"
    }
}

function New-EmptyState {
    [pscustomobject]@{
        schema_version = 1
        skill_name = 'revit-mcp-local-guidance'
        updated_at_utc = $null
        rules = @()
    }
}

function Normalize-State([object]$state) {
    if ($state.schema_version -ne 1 -or $state.skill_name -ne 'revit-mcp-local-guidance' -or $null -eq $state.rules) {
        throw 'The local learning state is invalid.'
    }
    $rules = @($state.rules)
    if ($rules.Count -gt $maxRules) { throw 'The local learning state exceeds the active-rule cap.' }
    $deduplicated = @{}
    $legacyBySignature = @{}
    foreach ($rule in $rules) {
        $legacyOwner = $rule.owner -eq 'setup-revit'
        if ($legacyOwner) {
            $rule.owner = 'diagnose-revit'
            $rule.signature = Get-Signature $rule.owner $rule.issue_id
            $script:stateNeedsMigration = $true
        }
        if ($rule.owner -notin @('diagnose-revit', 'inspect-revit', 'work-revit', 'document-revit') -or
            $rule.issue_id -isnot [string] -or $rule.issue_id -notmatch '^[a-z][a-z0-9-]{2,63}$' -or
            $rule.signature -ne (Get-Signature $rule.owner $rule.issue_id)) {
            throw 'The local learning state contains an invalid rule identity.'
        }
        Assert-SafeRuleText 'stored problem' $rule.problem
        Assert-SafeRuleText 'stored guidance' $rule.guidance
        if (-not $deduplicated.ContainsKey($rule.signature) -or ($legacyBySignature[$rule.signature] -and -not $legacyOwner)) {
            $deduplicated[$rule.signature] = $rule
            $legacyBySignature[$rule.signature] = $legacyOwner
        } else {
            $script:stateNeedsMigration = $true
        }
    }
    $state.rules = @($deduplicated.Values | Sort-Object owner, issue_id)
    return $state
}

function Read-State {
    $script:stateNeedsMigration = $false
    if (-not (Test-Path -LiteralPath $statePath)) { return New-EmptyState }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    return Normalize-State $state
}

function Assert-NoReparsePoint([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse points are not allowed in the managed local skill path: $Path"
        }
    }
}

function Repair-Promotion {
    if (-not (Test-Path -LiteralPath $journalPath)) { return }
    $journal = Get-Content -LiteralPath $journalPath -Raw | ConvertFrom-Json
    if ($journal.schema_version -ne 1 -or $journal.phase -notin @('prepared', 'old-moved')) {
        throw 'The local skill promotion journal is invalid.'
    }
    foreach ($entry in @('stage', 'active', 'backup')) {
        if ([string]::IsNullOrWhiteSpace($journal.$entry)) { throw 'The local skill promotion journal is incomplete.' }
        Assert-ChildPath $skillParent $journal.$entry
        Assert-NoReparsePoint $journal.$entry
    }
    if ([string]::IsNullOrWhiteSpace($journal.pending_state)) { throw 'The local skill promotion journal has no pending state.' }
    Assert-ChildPath $localRoot $journal.pending_state
    Assert-NoReparsePoint $journal.pending_state
    if ([IO.Path]::GetFullPath($journal.active) -ne [IO.Path]::GetFullPath($activeSkill) -or
        (Split-Path -Leaf $journal.stage) -notmatch '^\.revit-mcp-local-guidance\.stage-[a-f0-9]{32}$' -or
        (Split-Path -Leaf $journal.backup) -notmatch '^\.revit-mcp-local-guidance\.backup-[a-f0-9]{32}$' -or
        (Split-Path -Leaf $journal.pending_state) -notmatch '^pending-state-[a-f0-9]{32}\.json$') {
        throw 'The local skill promotion journal contains unexpected managed paths.'
    }
    if ($journal.phase -eq 'old-moved') {
        if (-not (Test-Path -LiteralPath $journal.active) -and (Test-Path -LiteralPath $journal.backup)) {
            Move-Item -LiteralPath $journal.backup -Destination $journal.active
            if (Test-Path -LiteralPath $journal.pending_state) { Remove-Item -LiteralPath $journal.pending_state -Force }
        } elseif ((Test-Path -LiteralPath $journal.active) -and (Test-Path -LiteralPath $journal.pending_state)) {
            Move-Item -LiteralPath $journal.pending_state -Destination $statePath -Force
        }
    }
    if (Test-Path -LiteralPath $journal.stage) { Remove-Item -LiteralPath $journal.stage -Recurse -Force }
    if (Test-Path -LiteralPath $journal.backup) { Remove-Item -LiteralPath $journal.backup -Recurse -Force }
    if (Test-Path -LiteralPath $journal.pending_state) { Remove-Item -LiteralPath $journal.pending_state -Force }
    Remove-Item -LiteralPath $journalPath -Force
}

function Get-Signature([string]$Owner, [string]$IssueId) {
    $normalized = ($Owner.Trim().ToLowerInvariant() + '|' + $IssueId.Trim().ToLowerInvariant())
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($normalized)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant().Substring(0, 20)
    } finally { $sha.Dispose() }
}

function Assert-SafeRuleText([string]$Name, [object]$Value) {
    if ($Value -isnot [string] -or [string]::IsNullOrWhiteSpace($Value) -or $Value.Length -gt $maxRuleChars) {
        throw "$Name must be a concise non-empty string of at most $maxRuleChars characters."
    }
    if ($Value -notmatch "^[A-Za-z0-9][A-Za-z0-9 .,;:()'_+-]*$") { throw "$Name contains unsupported characters." }
    $blocked = '(?i)(https?://|www\.|[A-Z]:\\|\\\\|/users/|/home/|@[^ ]+\.|password|secret|api[-_ ]?key|access[-_ ]?token|authorization|ignore (all |the )?(previous|policy)|powershell|cmd\.exe|shell command|git(hub)?|pull request|\bPR\b|publish|upload|download)'
    if ($Value -match $blocked) { throw "$Name contains private, executable, or delivery-oriented content." }
}

function Convert-Candidate([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw '-CandidatePath must point to a candidate JSON file.'
    }
    if ((Get-Item -LiteralPath $Path).Length -gt 32768) { throw 'Candidate JSON exceeds 32 KiB.' }
    $candidate = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $candidateKeys = @($candidate.psobject.Properties.Name)
    if ($candidate.schema_version -ne 1 -or $candidateKeys.Count -ne 3 -or
        ($candidateKeys | Where-Object { $_ -notin @('schema_version', 'rules', 'retire') })) {
        throw 'Candidate JSON has an invalid top-level schema.'
    }
    $updates = @($candidate.rules)
    $retire = @($candidate.retire)
    if ($updates.Count + $retire.Count -gt 2) { throw 'A weekly cycle may change at most two local rules.' }
    $owners = @('diagnose-revit', 'inspect-revit', 'work-revit', 'document-revit')
    $result = @()
    foreach ($rule in $updates) {
        $keys = @($rule.psobject.Properties.Name)
        if ($keys.Count -ne 5 -or ($keys | Where-Object { $_ -notin @('issue_id', 'owner', 'problem', 'guidance', 'evidence') })) {
            throw 'Each candidate rule must contain only issue_id, owner, problem, guidance, and evidence.'
        }
        if ($rule.owner -notin $owners) { throw 'Candidate rule owner is not a bundled Revit skill.' }
        if ($rule.issue_id -isnot [string] -or $rule.issue_id -notmatch '^[a-z][a-z0-9-]{2,63}$') {
            throw 'Candidate issue_id must be a stable lower-case issue identifier.'
        }
        Assert-SafeRuleText 'problem' $rule.problem
        Assert-SafeRuleText 'guidance' $rule.guidance
        $evidenceKeys = @($rule.evidence.psobject.Properties.Name)
        if ($evidenceKeys.Count -ne 4 -or ($evidenceKeys | Where-Object { $_ -notin @('occurrences', 'independent_sessions', 'deterministic_reproduction', 'explicit_correction') })) {
            throw 'Candidate evidence has an invalid schema.'
        }
        if ($rule.evidence.occurrences -isnot [int] -or $rule.evidence.independent_sessions -isnot [int] -or
            $rule.evidence.deterministic_reproduction -isnot [bool] -or $rule.evidence.explicit_correction -isnot [bool]) {
            throw 'Candidate evidence values have invalid types.'
        }
        $occurrences = [int]$rule.evidence.occurrences
        $sessions = [int]$rule.evidence.independent_sessions
        if ($occurrences -lt 0 -or $occurrences -gt 10000 -or $sessions -lt 0 -or $sessions -gt 10000 -or $sessions -gt $occurrences) {
            throw 'Candidate evidence counts are invalid.'
        }
        $repeated = $occurrences -ge 3 -and $sessions -ge 2
        $reproduced = $rule.evidence.deterministic_reproduction -eq $true -and $rule.evidence.explicit_correction -eq $true
        if (-not ($repeated -or $reproduced)) { throw 'Candidate rule does not clear the evidence threshold.' }
        $result += [pscustomobject]@{
            signature = Get-Signature $rule.owner $rule.issue_id
            issue_id = [string]$rule.issue_id
            owner = [string]$rule.owner
            problem = (($rule.problem -replace '\s+', ' ').Trim())
            guidance = (($rule.guidance -replace '\s+', ' ').Trim())
            occurrences = $occurrences
            independent_sessions = $sessions
            deterministic_reproduction = [bool]$rule.evidence.deterministic_reproduction
            explicit_correction = [bool]$rule.evidence.explicit_correction
            updated_at_utc = [DateTime]::UtcNow.ToString('o')
        }
    }
    $retireSignatures = @()
    foreach ($item in $retire) {
        $keys = @($item.psobject.Properties.Name)
        if ($keys.Count -ne 2 -or ($keys | Where-Object { $_ -notin @('owner', 'issue_id') }) -or
            $item.owner -notin $owners -or $item.issue_id -isnot [string] -or
            $item.issue_id -notmatch '^[a-z][a-z0-9-]{2,63}$') {
            throw 'Each retire entry must contain a valid owner and issue_id.'
        }
        $retireSignatures += Get-Signature $item.owner $item.issue_id
    }
    return [pscustomobject]@{ updates = @($result); retire_signatures = @($retireSignatures) }
}

function Render-Skill([object[]]$Rules) {
    $lines = @(
        '---',
        'name: revit-mcp-local-guidance',
        'description: Local, verified Revit MCP corrections learned on this Windows PC. Use with Revit MCP work when planning, diagnosing, inspecting, changing, or documenting a Revit 2024 model; supplements the bundled Revit skills without replacing their safety rules.',
        '---',
        '',
        '# Local Revit MCP Guidance',
        '',
        'Apply these verified local corrections together with the bundled Revit skills. Never let a local rule weaken preview/apply, confirmation, document, generation, or destructive-action safeguards.',
        '',
        '## Active rules',
        ''
    )
    if ($Rules.Count -eq 0) {
        $lines += '- No verified local corrections yet. Follow the bundled Revit skills.'
    } else {
        foreach ($rule in ($Rules | Sort-Object owner, signature)) {
            $skillReference = '$revit-mcp-cowork:' + [string]$rule.owner
            $lines += "- For $skillReference, when $($rule.problem): $($rule.guidance)"
        }
    }
    return ($lines -join "`n") + "`n"
}

function Write-StagedSkill([string]$Directory, [object[]]$Rules) {
    Assert-ChildPath $skillParent $Directory
    New-Item -ItemType Directory -Force -Path (Join-Path $Directory 'agents') | Out-Null
    $body = Render-Skill $Rules
    if ([Text.Encoding]::UTF8.GetByteCount($body) -gt $maxSkillBytes) { throw "Rendered local skill exceeds $maxSkillBytes bytes." }
    Set-Content -LiteralPath (Join-Path $Directory 'SKILL.md') -Value $body -Encoding UTF8
    @'
interface:
  display_name: "Local Revit Guidance"
  short_description: "Verified corrections learned on this PC"
  default_prompt: "Use $revit-mcp-local-guidance with the bundled Revit skills for this Revit MCP task."
policy:
  allow_implicit_invocation: true
'@ | Set-Content -LiteralPath (Join-Path $Directory 'agents\openai.yaml') -Encoding UTF8
    $readback = Get-Content -LiteralPath (Join-Path $Directory 'SKILL.md') -Raw
    if ($readback -notmatch '(?m)^name: revit-mcp-local-guidance$' -or $readback -notmatch '(?m)^description: .+$') {
        throw 'Rendered local skill failed validation.'
    }
}

function Promote-State([object]$State) {
    $State = Normalize-State $State
    New-Item -ItemType Directory -Force -Path $skillParent, $localRoot, $generationsRoot | Out-Null
    Repair-Promotion
    Assert-ChildPath $skillParent $activeSkill
    Assert-NoReparsePoint $activeSkill
    $token = [guid]::NewGuid().ToString('N')
    $stage = Join-Path $skillParent ".revit-mcp-local-guidance.stage-$token"
    $transientBackup = Join-Path $skillParent ".revit-mcp-local-guidance.backup-$token"
    $pendingState = Join-Path $localRoot "pending-state-$token.json"
    Assert-ChildPath $skillParent $stage
    Assert-ChildPath $skillParent $transientBackup
    Write-StagedSkill $stage @($State.rules)
    $generation = $null
    if (Test-Path -LiteralPath $activeSkill) {
        $generation = Join-Path $generationsRoot ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + $token)
        $generationStage = Join-Path $generationsRoot ('.stage-' + $token)
        New-Item -ItemType Directory -Force -Path (Join-Path $generationStage 'skill') | Out-Null
        Copy-Item -LiteralPath (Join-Path $activeSkill 'SKILL.md') -Destination (Join-Path $generationStage 'skill\SKILL.md')
        if (Test-Path -LiteralPath (Join-Path $activeSkill 'agents\openai.yaml')) {
            New-Item -ItemType Directory -Force -Path (Join-Path $generationStage 'skill\agents') | Out-Null
            Copy-Item -LiteralPath (Join-Path $activeSkill 'agents\openai.yaml') -Destination (Join-Path $generationStage 'skill\agents\openai.yaml')
        }
        Write-JsonAtomic (Join-Path $generationStage 'state.json') (Read-State)
        if (-not (Test-Path -LiteralPath (Join-Path $generationStage 'skill\SKILL.md')) -or
            -not (Test-Path -LiteralPath (Join-Path $generationStage 'state.json'))) {
            throw 'The known-good generation could not be staged.'
        }
        Move-Item -LiteralPath $generationStage -Destination $generation
    }
    $State.updated_at_utc = [DateTime]::UtcNow.ToString('o')
    Write-JsonAtomic $pendingState $State
    Write-JsonAtomic $journalPath ([pscustomobject]@{ schema_version = 1; stage = $stage; active = $activeSkill; backup = $transientBackup; pending_state = $pendingState; phase = 'prepared' })
    try {
        if (Test-Path -LiteralPath $activeSkill) { Move-Item -LiteralPath $activeSkill -Destination $transientBackup }
        Write-JsonAtomic $journalPath ([pscustomobject]@{ schema_version = 1; stage = $stage; active = $activeSkill; backup = $transientBackup; pending_state = $pendingState; phase = 'old-moved' })
        Move-Item -LiteralPath $stage -Destination $activeSkill
        if (-not (Test-Path -LiteralPath (Join-Path $activeSkill 'SKILL.md'))) { throw 'Local skill promotion readback failed.' }
        Move-Item -LiteralPath $pendingState -Destination $statePath -Force
        if (Test-Path -LiteralPath $transientBackup) { Remove-Item -LiteralPath $transientBackup -Recurse -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $journalPath) { Remove-Item -LiteralPath $journalPath -Force -ErrorAction SilentlyContinue }
    } catch {
        if (Test-Path -LiteralPath $activeSkill) { Remove-Item -LiteralPath $activeSkill -Recurse -Force }
        if (Test-Path -LiteralPath $transientBackup) { Move-Item -LiteralPath $transientBackup -Destination $activeSkill }
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        if (Test-Path -LiteralPath $pendingState) { Remove-Item -LiteralPath $pendingState -Force }
        throw
    }
    Get-ChildItem -LiteralPath $generationsRoot -Directory -Filter '.stage-*' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    $old = @(Get-ChildItem -LiteralPath $generationsRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{8}T\d{9}Z-[a-f0-9]{32}$' } |
        Sort-Object Name -Descending | Select-Object -Skip 2)
    foreach ($item in $old) {
        Assert-ChildPath $generationsRoot $item.FullName
        Remove-Item -LiteralPath $item.FullName -Recurse -Force
    }
}

$mutexHash = Get-Signature 'mutex' $pluginData
$mutex = New-Object Threading.Mutex($false, "Local\RevitMcpLearning-$mutexHash")
$mutexHeld = $false
try {
    try { $mutexHeld = $mutex.WaitOne(15000) } catch [Threading.AbandonedMutexException] { $mutexHeld = $true }
    if (-not $mutexHeld) { throw 'Another Revit learning update is already running.' }
    if ($Action -in @('InitializeLocal', 'ApplyLocal', 'CompleteRun', 'RollbackLocal', 'LocalStatus')) {
        New-Item -ItemType Directory -Force -Path $skillParent, $localRoot | Out-Null
        Repair-Promotion
    }
switch ($Action) {
    'Enable' {
        if (Test-Path -LiteralPath $disabled) { Remove-Item -LiteralPath $disabled -Force }
        Write-Output 'Revit learning evidence collection is enabled.'
    }
    'Disable' {
        New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
        New-Item -ItemType File -Force -Path $disabled | Out-Null
        Write-Output 'Revit learning evidence collection is disabled.'
    }
    'Delete' {
        if (Test-Path -LiteralPath $evidenceRoot) {
            Get-ChildItem -LiteralPath $evidenceRoot -File |
                Where-Object { $_.Name -match '^events(?:\.1)?\.jsonl$' } |
                Remove-Item -Force
        }
        Write-Output 'Sanitized Revit learning evidence was deleted.'
    }
    'Export' {
        if ([string]::IsNullOrWhiteSpace($ExportPath)) { throw '-ExportPath is required for Export.' }
        New-Item -ItemType Directory -Force -Path $ExportPath | Out-Null
        Get-ChildItem -LiteralPath $evidenceRoot -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^events(?:\.1)?\.jsonl$' } |
            Copy-Item -Destination $ExportPath -Force
        Write-Output "Sanitized evidence exported to $ExportPath"
    }
    'InitializeLocal' {
        Assert-NoReparsePoint $activeSkill
        if (Test-Path -LiteralPath $activeSkill) {
            if (-not (Test-Path -LiteralPath $statePath)) { throw 'A colliding unmanaged local skill already exists.' }
            $state = Read-State
            if ($script:stateNeedsMigration) {
                Promote-State $state
                Write-Output 'Local Revit guidance was migrated and is ready.'
            } else {
                Write-Output 'Local Revit guidance is already initialized.'
            }
        } else {
            $state = New-EmptyState
            Promote-State $state
            Write-Output 'Local Revit guidance was initialized.'
        }
    }
    'ApplyLocal' {
        $parsedCandidate = Convert-Candidate $CandidatePath
        $updates = @($parsedCandidate.updates)
        $retireSignatures = @($parsedCandidate.retire_signatures)
        $state = Read-State
        $rules = [Collections.ArrayList]@(@($state.rules))
        $changed = $script:stateNeedsMigration
        foreach ($retireSignature in $retireSignatures) {
            for ($index = $rules.Count - 1; $index -ge 0; $index--) {
                if ($rules[$index].signature -eq $retireSignature) {
                    $rules.RemoveAt($index)
                    $changed = $true
                }
            }
        }
        foreach ($update in $updates) {
            $existingIndex = -1
            for ($index = 0; $index -lt $rules.Count; $index++) {
                if ($rules[$index].signature -eq $update.signature) { $existingIndex = $index; break }
            }
            if ($existingIndex -ge 0) {
                if ($rules[$existingIndex].guidance -ne $update.guidance) {
                    $rules[$existingIndex] = $update
                    $changed = $true
                }
            } else {
                [void]$rules.Add($update)
                $changed = $true
            }
        }
        if ($rules.Count -gt $maxRules) { throw "Local guidance is capped at $maxRules active rules; consolidate before adding another." }
        if (-not $changed) {
            Write-Output 'Local Revit guidance already contains the candidate rule(s); no update was needed.'
            break
        }
        $state.rules = @($rules)
        Promote-State $state
        Write-Output "Local Revit guidance now contains $($rules.Count) verified rule(s)."
    }
    'CompleteRun' {
        if ([string]::IsNullOrWhiteSpace($WatermarkUtc)) { throw '-WatermarkUtc is required for CompleteRun.' }
        $watermark = [DateTimeOffset]::Parse($WatermarkUtc).ToUniversalTime()
        if ($watermark -gt [DateTimeOffset]::UtcNow.AddMinutes(5)) { throw 'The checkpoint watermark cannot be future-dated.' }
        Write-JsonAtomic $checkpointPath ([pscustomobject]@{ schema_version = 1; last_successful_watermark_utc = $watermark.ToString('o') })
        Write-Output 'The successful review checkpoint was advanced.'
    }
    'RollbackLocal' {
        $generation = Get-ChildItem -LiteralPath $generationsRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -match '^\d{8}T\d{9}Z-[a-f0-9]{32}$' -and
                (Test-Path -LiteralPath (Join-Path $_.FullName 'skill\SKILL.md')) -and
                (Test-Path -LiteralPath (Join-Path $_.FullName 'state.json'))
            } | Sort-Object Name -Descending | Select-Object -First 1
        if ($null -eq $generation) { throw 'No known-good local guidance generation is available.' }
        $restoredState = Get-Content -LiteralPath (Join-Path $generation.FullName 'state.json') -Raw | ConvertFrom-Json
        Promote-State $restoredState
        Write-Output 'Local Revit guidance was rolled back to the latest known-good generation.'
    }
    'LocalStatus' {
        $state = Read-State
        [pscustomobject]@{
            Initialized = (Test-Path -LiteralPath (Join-Path $activeSkill 'SKILL.md'))
            ActiveRules = @($state.rules).Count
            ActiveSkill = $activeSkill
            State = $statePath
            Checkpoint = $checkpointPath
            LastUpdatedUtc = $state.updated_at_utc
        }
    }
    default {
        $files = @(Get-ChildItem -LiteralPath $evidenceRoot -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^events(?:\.1)?\.jsonl$' })
        [pscustomobject]@{
            Enabled = -not (Test-Path -LiteralPath $disabled)
            EvidenceFiles = $files.Count
            EvidenceBytes = ($files | Measure-Object Length -Sum).Sum
            Location = $evidenceRoot
        }
    }
}
} finally {
    if ($mutexHeld) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
