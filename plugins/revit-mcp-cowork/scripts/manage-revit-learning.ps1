param(
    [ValidateSet('Status', 'Enable', 'Disable', 'Delete', 'Export')]
    [string]$Action = 'Status',
    [string]$ExportPath
)

$ErrorActionPreference = 'Stop'
$locator = Join-Path $env:LOCALAPPDATA 'RevitMcpNext\CodexLearning\plugin-data-location.json'
if (-not (Test-Path $locator)) {
    throw 'No learning data location exists yet. Trust the plugin hook and run a Revit MCP tool first.'
}
$pluginData = (Get-Content $locator -Raw | ConvertFrom-Json).plugin_data
$evidenceRoot = Join-Path $pluginData 'learning-evidence'
$disabled = Join-Path $evidenceRoot 'disabled'

switch ($Action) {
    'Enable' {
        if (Test-Path $disabled) { Remove-Item -LiteralPath $disabled -Force }
        Write-Output 'Revit learning evidence collection is enabled.'
    }
    'Disable' {
        New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
        New-Item -ItemType File -Force -Path $disabled | Out-Null
        Write-Output 'Revit learning evidence collection is disabled.'
    }
    'Delete' {
        if (Test-Path $evidenceRoot) {
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
    default {
        $files = @(Get-ChildItem -LiteralPath $evidenceRoot -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^events(?:\.1)?\.jsonl$' })
        [pscustomobject]@{
            Enabled = -not (Test-Path $disabled)
            EvidenceFiles = $files.Count
            EvidenceBytes = ($files | Measure-Object Length -Sum).Sum
            Location = $evidenceRoot
        }
    }
}
