[CmdletBinding()]
param(
    [string]$PluginSource = "https://github.com/BhaveshY/revit-mcp-codex-plugin",
    [string]$PluginSelector = "revit-mcp-cowork@revit-mcp-codex-plugin",
    [string]$RevitVersion = "2024",
    [string]$NodeVersion = "22.22.3",
    [switch]$SkipNode,
    [switch]$SkipMcpServer,
    [switch]$SkipRevitAddin,
    [switch]$SkipCodexPlugin
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Add-UserPathEntry {
    param([string]$PathToAdd)

    $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $userParts = @()
    if ($currentUserPath) {
        $userParts = $currentUserPath -split ";" | Where-Object { $_ }
    }

    if ($userParts -notcontains $PathToAdd) {
        $userParts = @($PathToAdd) + $userParts
        [Environment]::SetEnvironmentVariable("Path", ($userParts -join ";"), "User")
    }

    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $machineParts = @()
    if ($machinePath) {
        $machineParts = $machinePath -split ";" | Where-Object { $_ }
    }

    $env:Path = ((@($PathToAdd) + $userParts + $machineParts) | Select-Object -Unique) -join ";"
}

function Require-Command {
    param(
        [string]$Name,
        [string]$InstallHint
    )

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "$Name was not found. $InstallHint"
    }
    return $cmd.Source
}

function Run-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

if ($RevitVersion -ne "2024") {
    throw "This helper currently installs the tested Revit 2024 addin only. Pass -SkipRevitAddin for other Revit versions."
}

$nodeDir = Join-Path $env:USERPROFILE ".local\nodejs22"
$nodeExe = Join-Path $nodeDir "node.exe"
$npmCmd = Join-Path $nodeDir "npm.cmd"

if (-not $SkipNode) {
    if (Test-Path -LiteralPath $nodeExe) {
        Write-Step "Using existing Node install at $nodeDir"
        Add-UserPathEntry $nodeDir
        Run-Checked $nodeExe @("--version")
    }
    else {
        Write-Step "Installing Node.js v$NodeVersion to $nodeDir"
        $downloadRoot = Join-Path $env:TEMP ("revit-mcp-node-" + [Guid]::NewGuid().ToString("N"))
        $zipPath = Join-Path $downloadRoot "node.zip"
        $extractRoot = Join-Path $downloadRoot "extract"
        $nodeUrl = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"

        New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
        New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
        Invoke-WebRequest -Uri $nodeUrl -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

        $expandedNodeDir = Join-Path $extractRoot "node-v$NodeVersion-win-x64"
        if (-not (Test-Path -LiteralPath $expandedNodeDir)) {
            throw "Node archive did not contain expected folder: $expandedNodeDir"
        }

        New-Item -ItemType Directory -Force -Path $nodeDir | Out-Null
        Copy-Item -Path (Join-Path $expandedNodeDir "*") -Destination $nodeDir -Recurse -Force
        Add-UserPathEntry $nodeDir
        Run-Checked $nodeExe @("--version")
    }
}
else {
    Write-Step "Skipping Node install"
}

if (-not (Test-Path -LiteralPath $npmCmd)) {
    $npmFromPath = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($npmFromPath) {
        $npmCmd = $npmFromPath.Source
    }
}

if (-not $SkipMcpServer) {
    Write-Step "Installing mcp-server-for-revit npm package"
    if (-not (Test-Path -LiteralPath $npmCmd)) {
        $npmCmd = Require-Command "npm.cmd" "Install Node.js 22 LTS, then rerun this script."
    }
    Run-Checked $npmCmd @("install", "-g", "mcp-server-for-revit")
}
else {
    Write-Step "Skipping npm bridge install"
}

if (-not $SkipRevitAddin) {
    Write-Step "Installing Revit $RevitVersion addin"
    $assetName = "mcp-servers-for-revit-v1.0.0-Revit$RevitVersion.zip"
    $addinUrl = "https://github.com/mcp-servers-for-revit/mcp-servers-for-revit/releases/download/v1.0.0/$assetName"
    $addinDir = Join-Path $env:APPDATA "Autodesk\Revit\Addins\$RevitVersion"
    $downloadRoot = Join-Path $env:TEMP ("revit-mcp-addin-" + [Guid]::NewGuid().ToString("N"))
    $zipPath = Join-Path $downloadRoot $assetName
    $extractRoot = Join-Path $downloadRoot "extract"

    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $addinDir | Out-Null

    $existingAddins = Get-ChildItem -LiteralPath $addinDir -Force -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existingAddins) {
        $backupDir = "$addinDir.backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
        Write-Host "Backing up existing addin folder to $backupDir"
        Copy-Item -LiteralPath $addinDir -Destination $backupDir -Recurse -Force
    }

    Invoke-WebRequest -Uri $addinUrl -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

    $manifest = Get-ChildItem -LiteralPath $extractRoot -Recurse -Filter "*.addin" | Select-Object -First 1
    if (-not $manifest) {
        throw "Downloaded Revit addin archive did not contain a .addin manifest."
    }

    Copy-Item -Path (Join-Path $manifest.Directory.FullName "*") -Destination $addinDir -Recurse -Force
    Write-Host "Revit addin installed to $addinDir"
}
else {
    Write-Step "Skipping Revit addin install"
}

if (-not $SkipCodexPlugin) {
    Write-Step "Installing Codex plugin from $PluginSource"
    $codexCmd = Require-Command "codex" "Install Codex Desktop or make sure codex.exe is available in PowerShell."
    Run-Checked $codexCmd @("plugin", "marketplace", "add", $PluginSource, "--json")
    Run-Checked $codexCmd @("plugin", "add", $PluginSelector, "--json")
    Run-Checked $codexCmd @("mcp", "get", "revit")
}
else {
    Write-Step "Skipping Codex plugin install"
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "1. Fully quit and reopen Codex Desktop."
Write-Host "2. Start Revit $RevitVersion, choose Always Load if prompted, and open a project."
Write-Host "3. Start the Revit MCP listener in Revit."
Write-Host "4. In Codex Desktop, ask: Run a Revit health check."
