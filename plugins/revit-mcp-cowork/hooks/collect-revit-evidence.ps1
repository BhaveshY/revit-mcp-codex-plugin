$ErrorActionPreference = "Stop"

if ($env:REVIT_MCP_LEARNING -match '^(0|false|off)$') { exit 0 }
if ([string]::IsNullOrWhiteSpace($env:PLUGIN_DATA)) { exit 0 }

function Get-ShortHash([string]$Value) {
    if ([string]::IsNullOrEmpty($Value)) { return $null }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').Substring(0, 16).ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Get-AllowlistedShape($Value, [string[]]$AllowedKeys, [int]$MaxDepth) {
    $allowed = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($key in $AllowedKeys) { [void]$allowed.Add($key) }
    return @(Get-ShapePaths $Value '' 0 $MaxDepth $allowed)
}

function Get-ShapePaths($Value, [string]$Prefix, [int]$Depth, [int]$MaxDepth, $AllowedKeys) {
    if ($Depth -gt $MaxDepth -or $null -eq $Value) { return @() }
    $paths = [Collections.Generic.List[string]]::new()
    if ($Value -is [Collections.IDictionary]) {
        foreach ($key in @($Value.Keys | Sort-Object | Select-Object -First 64)) {
            if (-not $AllowedKeys.Contains([string]$key)) { continue }
            $path = if ($Prefix) { "$Prefix.$key" } else { [string]$key }
            $paths.Add($path)
            foreach ($child in Get-ShapePaths $Value[$key] $path ($Depth + 1) $MaxDepth $AllowedKeys) { $paths.Add($child) }
        }
    } elseif ($Value -is [pscustomobject]) {
        foreach ($property in @($Value.PSObject.Properties | Sort-Object Name | Select-Object -First 64)) {
            if (-not $AllowedKeys.Contains($property.Name)) { continue }
            $path = if ($Prefix) { "$Prefix.$($property.Name)" } else { $property.Name }
            $paths.Add($path)
            foreach ($child in Get-ShapePaths $property.Value $path ($Depth + 1) $MaxDepth $AllowedKeys) { $paths.Add($child) }
        }
    } elseif ($Value -is [Collections.IEnumerable] -and $Value -isnot [string]) {
        $paths.Add($(if ($Prefix) { "$Prefix[]" } else { '[]' }))
        $first = @($Value | Select-Object -First 1)
        if ($first.Count) {
            foreach ($child in Get-ShapePaths $first[0] "$Prefix[]" ($Depth + 1) $MaxDepth $AllowedKeys) { $paths.Add($child) }
        }
    }
    return @($paths | Select-Object -Unique | Select-Object -First 96)
}

function Find-NormalizedCode($Value, [int]$Depth = 0) {
    if ($Depth -gt 6 -or $null -eq $Value) { return $null }
    $properties = if ($Value -is [Collections.IDictionary]) {
        @($Value.Keys | ForEach-Object { [pscustomobject]@{ Name = [string]$_; Value = $Value[$_] } })
    } elseif ($Value -is [pscustomobject]) { @($Value.PSObject.Properties) } else { @() }
    foreach ($property in $properties) {
        if ($property.Name -match '^(errorCode|error_code|reasonCode)$') {
            $candidate = [string]$property.Value
            if ($candidate -match '^[A-Z][A-Z0-9_]{2,63}$') { return $candidate }
        }
    }
    foreach ($property in $properties) {
        $found = Find-NormalizedCode $property.Value ($Depth + 1)
        if ($found) { return $found }
    }
    if ($Value -is [Collections.IEnumerable] -and $Value -isnot [string]) {
        foreach ($item in @($Value | Select-Object -First 16)) {
            $found = Find-NormalizedCode $item ($Depth + 1)
            if ($found) { return $found }
        }
    }
    return $null
}

function Find-ErrorFlag($Value, [int]$Depth = 0) {
    if ($Depth -gt 6 -or $null -eq $Value) { return $false }
    $properties = if ($Value -is [Collections.IDictionary]) {
        @($Value.Keys | ForEach-Object { [pscustomobject]@{ Name = [string]$_; Value = $Value[$_] } })
    } elseif ($Value -is [pscustomobject]) { @($Value.PSObject.Properties) } else { @() }
    foreach ($property in $properties) {
        if ($property.Name -match '^(isError|error|failed)$' -and $property.Value -eq $true) { return $true }
        if ($property.Name -eq 'success' -and $property.Value -eq $false) { return $true }
    }
    foreach ($property in $properties) {
        if (Find-ErrorFlag $property.Value ($Depth + 1)) { return $true }
    }
    return $false
}

try {
    $payloadText = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($payloadText)) { exit 0 }
    $payload = $payloadText | ConvertFrom-Json
    if ($payload.hook_event_name -ne 'PostToolUse') { exit 0 }
    if ([string]$payload.tool_name -notmatch '^(mcp__revit-mcp-next__.*|revit\..*)$') { exit 0 }

    $dataRoot = [IO.Path]::GetFullPath($env:PLUGIN_DATA)
    $evidenceRoot = Join-Path $dataRoot 'learning-evidence'
    New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
    if (Test-Path (Join-Path $evidenceRoot 'disabled')) { exit 0 }

    $pluginVersion = $null
    if ($env:PLUGIN_ROOT) {
        $manifest = Join-Path $env:PLUGIN_ROOT '.codex-plugin\plugin.json'
        if (Test-Path $manifest) { $pluginVersion = (Get-Content $manifest -Raw | ConvertFrom-Json).version }
    }

    $code = Find-NormalizedCode $payload.tool_response
    $isError = Find-ErrorFlag $payload.tool_response
    $knownCodes = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    if ($env:PLUGIN_ROOT) {
        $catalogPath = Join-Path $env:PLUGIN_ROOT 'learning\capabilities.json'
        if (Test-Path $catalogPath) {
            $catalog = Get-Content $catalogPath -Raw | ConvertFrom-Json
            foreach ($skill in @($catalog.skills)) {
                foreach ($knownCode in @($skill.failure_codes)) { [void]$knownCodes.Add([string]$knownCode) }
            }
        }
    }
    if (-not $isError) { $code = $null }
    elseif (-not $code -or -not $knownCodes.Contains($code)) { $code = 'UNKNOWN_ERROR' }
    $inputKeys = @('operations','previewId','baseGeneration','changeSetHash','expiresAt','confirm','documentId','generation','cursor','pageSize','query','filters','category','categories','elementIds','viewId','sheetId','scheduleId','roomIds','parameters','typeId','familyId','levelId','projectName','action','options')
    $responseKeys = @('isError','success','structuredContent','errorCode','error_code','reasonCode','status','result','data','meta','documentId','generation','previewId','baseGeneration','changeSetHash','expiresAt','cursor','items','warnings','validation','message')
    $event = [ordered]@{
        schema_version = 1
        timestamp_utc = [DateTime]::UtcNow.ToString('o')
        session_hash = Get-ShortHash ([string]$payload.session_id)
        turn_hash = Get-ShortHash ([string]$payload.turn_id)
        tool_name = [string]$payload.tool_name
        plugin_version = $pluginVersion
        outcome = $(if ($isError) { 'error' } else { 'success' })
        error_code = $code
        input_shape = @(Get-AllowlistedShape $payload.tool_input $inputKeys 0)
        response_shape = @(Get-AllowlistedShape $payload.tool_response $responseKeys 2)
    }
    $line = ($event | ConvertTo-Json -Compress -Depth 8) + [Environment]::NewLine
    $lineBytes = [Text.Encoding]::UTF8.GetByteCount($line)
    if ($lineBytes -gt 16384) { exit 0 }

    $mutexName = 'Local\RevitMcpLearning_' + (Get-ShortHash $evidenceRoot)
    $mutex = [Threading.Mutex]::new($false, $mutexName)
    try {
        if (-not $mutex.WaitOne(2000)) { exit 0 }
        $eventsPath = Join-Path $evidenceRoot 'events.jsonl'
        if ((Test-Path $eventsPath) -and ((Get-Item $eventsPath).Length + $lineBytes) -gt 5242880) {
            $backup = Join-Path $evidenceRoot 'events.1.jsonl'
            if (Test-Path $backup) { Remove-Item -LiteralPath $backup -Force }
            Move-Item -LiteralPath $eventsPath -Destination $backup
        }
        [IO.File]::AppendAllText($eventsPath, $line, [Text.UTF8Encoding]::new($false))

        $pruneMarker = Join-Path $evidenceRoot 'last-pruned.txt'
        $shouldPrune = -not (Test-Path $pruneMarker) -or (Get-Item $pruneMarker).LastWriteTimeUtc -lt [DateTime]::UtcNow.AddDays(-1)
        if ($shouldPrune) {
            $cutoff = [DateTime]::UtcNow.AddDays(-30)
            foreach ($logPath in @((Join-Path $evidenceRoot 'events.1.jsonl'), $eventsPath)) {
                if (-not (Test-Path $logPath)) { continue }
                $kept = [Collections.Generic.List[string]]::new()
                foreach ($existingLine in [IO.File]::ReadLines($logPath)) {
                    try {
                        $existingEvent = $existingLine | ConvertFrom-Json
                        $timestamp = [DateTimeOffset]::Parse([string]$existingEvent.timestamp_utc).UtcDateTime
                        if ($timestamp -ge $cutoff -and $timestamp -le [DateTime]::UtcNow.AddMinutes(5)) { $kept.Add($existingLine) }
                    } catch {}
                }
                [IO.File]::WriteAllLines($logPath, $kept, [Text.UTF8Encoding]::new($false))
            }
            [IO.File]::WriteAllText($pruneMarker, [DateTime]::UtcNow.ToString('o'), [Text.UTF8Encoding]::new($false))
        }

        if ($env:LOCALAPPDATA) {
            $locatorRoot = Join-Path $env:LOCALAPPDATA 'RevitMcpNext\CodexLearning'
            New-Item -ItemType Directory -Force -Path $locatorRoot | Out-Null
            [ordered]@{ schema_version = 1; plugin_data = $dataRoot } |
                ConvertTo-Json -Compress |
                Set-Content -LiteralPath (Join-Path $locatorRoot 'plugin-data-location.json') -Encoding UTF8
        }
    } finally {
        try { $mutex.ReleaseMutex() } catch {}
        $mutex.Dispose()
    }
} catch {
    # Evidence collection is advisory and must never disrupt Revit work.
    exit 0
}
