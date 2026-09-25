<#
.SYNOPSIS
    Wrap the Nuitka standalone build into a Windows MSI installer (WiX v7).

.DESCRIPTION
    The Windows counterpart of `make package` (which produces a .dmg on macOS).
    Assumes `make build` (scripts/_build_app.ps1) has already produced
    dist\StemGenApp.dist\StemGenApp.exe, then compiles
    scripts/wix/stemgen.wxs into a single self-contained MSI plus a
    SHA-256 sidecar.

    Naming convention (mirrors Track Kommander):
        build-*    compile to executable (Nuitka)        -> StemGenApp.exe
        package-*  wrap into a distributable (this file)  -> MSI

    Output (under <repo>\dist\):
        StemGenSetup[-<ts>].msi          self-contained installer
        StemGenSetup[-<ts>].msi.sha256   checksum

    NOTE: ASCII-only on purpose - Windows PowerShell 5.1 corrupts non-ASCII
    glyphs in BOM-less .ps1 files, which breaks parsing.

.PARAMETER Timestamp
    Append a yyyy-MM-dd_HH-mm-ss suffix so dated builds pile up without
    overwriting. `make package` passes this; call the script directly (no
    switch) for a stable, un-suffixed name suitable for versioned renaming.

.PARAMETER WixOnly
    Skip the build-output existence guard's "run make build" hint wording -
    reserved for fast .wxs iteration once a bundle already exists. (The guard
    still runs; the bundle must be present either way.)
#>
[CmdletBinding()]
param(
    [switch]$Timestamp,
    [switch]$WixOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---- Inputs -----------------------------------------------------------------
function Get-EnvOr {
    param([string]$Name, [string]$Default)
    $v = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrEmpty($v)) { return $Default }
    return $v
}

$AppName  = Get-EnvOr 'APP_NAME' 'StemGen'
$Dist     = Get-EnvOr 'DIST'     'dist'
# StemGenSetup (cpu) or StemGenSetup-CUDA - set by make.ps1 -Variant.
$MsiStem  = Get-EnvOr 'MSI_STEM' 'StemGenSetup'

# Repo root = parent of scripts\. Resolve absolute dist + wix paths so the
# `wix build` run (which we launch from scripts\wix\) writes to the right place.
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot
$DistDir   = Join-Path $RepoRoot $Dist
$WixDir    = Join-Path $RepoRoot 'scripts\wix'
$BuildExe  = Join-Path $DistDir 'StemGenApp.dist\StemGenApp.exe'
$WxsFile   = 'stemgen.wxs'    # relative to $WixDir

# ---- Guard: the Nuitka bundle must exist ------------------------------------
if (-not (Test-Path $BuildExe)) {
    $hint = if ($WixOnly) { "the bundle is missing" } else { "run 'make build' first" }
    throw "Build output not found at $BuildExe - $hint."
}

# ---- MSI ProductVersion -----------------------------------------------------
# Monotonic, host-independent: 1.0.<whole days since 2020-01-01 UTC>. Fits MSI's
# 0-65535 third-field limit until ~2199. MajorUpgrade only removes a strictly
# lower version, so this keeps Add/Remove Programs to a single entry across
# rebuilds. Override with STEMGEN_MSI_BUILD (keep it monotonic).
$msiBuild = Get-EnvOr 'STEMGEN_MSI_BUILD' ''
if ([string]::IsNullOrEmpty($msiBuild)) {
    $days = [int]([DateTime]::UtcNow.Date - [DateTime]::new(2020, 1, 1)).TotalDays
    $msiBuild = "$days"
}
$msiVersion = "1.0.$msiBuild"

# ---- Artefact base name (optionally timestamped) ----------------------------
$base = $MsiStem
if ($Timestamp) {
    $ts = (Get-Date -Format 'yyyy-MM-dd_HH-mm-ss')
    $base = "$MsiStem-$ts"
}
$msiOut = Join-Path $DistDir "$base.msi"

Write-Host "=== StemGen Windows installer ===" -ForegroundColor Cyan
Write-Host "  MSI ProductVersion: $msiVersion"
Write-Host "  Output:             $msiOut"
Write-Host ""

# ---- Ensure WiX tooling -----------------------------------------------------
# wix is a global dotnet tool. Auto-install/extension-add so a clean box can
# package without manual setup. -acceptEula wix7 is required by WiX v7's OSMF
# gate on every invocation.
function Ensure-Wix {
    if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
        throw "dotnet SDK not found on PATH. Install from https://aka.ms/dotnet/download, then re-run."
    }
    if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
        Write-Host "-> installing WiX global tool (dotnet tool install --global wix)" -ForegroundColor Yellow
        & dotnet tool install --global wix | Out-Null
        # Make the freshly-installed shim visible without a new shell.
        $env:PATH = "$env:USERPROFILE\.dotnet\tools;$env:PATH"
        if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
            throw "WiX install failed. Run manually: dotnet tool install --global wix"
        }
    }
    # Extensions are idempotent to add; swallow 'already added' noise.
    & wix extension add WixToolset.UI.wixext   --global -acceptEula wix7 2>$null | Out-Null
    & wix extension add WixToolset.Util.wixext --global -acceptEula wix7 2>$null | Out-Null
}
Ensure-Wix

# ---- Clean prior artefacts for this base name -------------------------------
foreach ($f in @("$base.msi", "$base.msi.sha256", "$base.wixpdb")) {
    $p = Join-Path $DistDir $f
    if (Test-Path $p) { Remove-Item $p -Force }
}
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir -Force | Out-Null }

# ---- Compile the MSI --------------------------------------------------------
# Run from scripts\wix so the relative paths inside the .wxs (..\..\dist\...,
# ..\..\assets\icons\tk.ico, license.rtf) resolve exactly as authored.
Push-Location $WixDir
try {
    Write-Host "-> wix build $WxsFile" -ForegroundColor Cyan
    & wix build $WxsFile `
        -acceptEula wix7 `
        -arch x64 `
        -d "Version=$msiVersion" `
        -d "BundleDir=..\..\$Dist\StemGenApp.dist" `
        -ext WixToolset.UI.wixext `
        -ext WixToolset.Util.wixext `
        -o $msiOut
    if ($LASTEXITCODE -ne 0) { throw "wix build failed (exit $LASTEXITCODE)" }
}
finally {
    Pop-Location
}

# WiX writes a .wixpdb sidecar next to the MSI; we ship a single file.
$wixpdb = Join-Path $DistDir "$base.wixpdb"
if (Test-Path $wixpdb) { Remove-Item $wixpdb -Force }

if (-not (Test-Path $msiOut)) { throw "wix reported success but $msiOut is missing" }

# ---- SHA-256 sidecar (parity with package-macos.sh) -------------------------
$hash = (Get-FileHash $msiOut -Algorithm SHA256).Hash.ToLower()
$sidecar = "$msiOut.sha256"
Set-Content -NoNewline -Encoding ascii -Path $sidecar -Value "$hash  $base.msi"

$sizeMb = [math]::Round((Get-Item $msiOut).Length / 1MB, 1)
Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "  Installer: $msiOut  ($sizeMb MB)"
Write-Host "  Checksum:  $sidecar"
Write-Host ""
Write-Host "  Install:        msiexec /i `"$msiOut`""
Write-Host "  Silent install: msiexec /i `"$msiOut`" /quiet /norestart"
Write-Host "  Uninstall:      msiexec /x `"$msiOut`" /quiet"
