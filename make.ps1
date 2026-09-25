<#
.SYNOPSIS
    StemGen - Windows task runner (PowerShell equivalent of the Makefile).

.DESCRIPTION
    Mirrors the Makefile targets so Windows users get the same workflow without
    needing GNU Make + POSIX tools. The Makefile delegates here on Windows, but
    you can also call it directly:

        .\make.ps1 build
        .\make.ps1 package -Variant cuda

    -Variant picks the torch build (default: cpu):
        cpu    PyPI torch, CPU only        .venv       dist\       StemGenSetup-<ts>.msi
        cuda   CUDA 13 torch (NVIDIA GPU)  .venv-cuda  dist-cuda\  StemGenSetup-CUDA-<ts>.msi
    Each variant keeps its own venv and dist so switching never reinstalls
    ~2 GB of torch. Both MSIs share one UpgradeCode: installing one replaces
    the other.

    Targets:
        help        list targets
        venv        uv sync - create/refresh .venv (runtime + build deps)
        lock        uv lock - refresh uv.lock
        run         run the app from source
        test        run the unit tests
        build       Nuitka compile -> dist\StemGenApp.dist\StemGenApp.exe
        package     build + wrap into dist\StemGenSetup-<ts>.msi (WiX)
        clean       remove dist\, build\
        distclean   clean + remove .venv

    'sync' is kept as a hidden alias of 'venv' for muscle memory.

    NOTE: this file is intentionally ASCII-only. Windows PowerShell 5.1 reads
    .ps1 files in the legacy ANSI codepage when there is no BOM, which corrupts
    non-ASCII glyphs and breaks parsing. Keep it plain ASCII.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Target = 'help',
    [ValidateSet('cpu', 'cuda')]
    [string]$Variant = 'cpu'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---- Config (kept in sync with the Makefile) --------------------------------
$AppName       = 'StemGen'
$Entry         = 'src/StemGenApp.py'
$PythonVersion = '3.13'
$Venv          = if ($Variant -eq 'cuda') { '.venv-cuda' } else { '.venv' }
$Dist          = if ($Variant -eq 'cuda') { 'dist-cuda' } else { 'dist' }
$MsiStem       = if ($Variant -eq 'cuda') { 'StemGenSetup-CUDA' } else { 'StemGenSetup' }
$VenvPy        = Join-Path $Venv 'Scripts\python.exe'

# Run from the repo root regardless of where the caller invoked us.
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

# ---- Helpers ----------------------------------------------------------------

function Resolve-Uv {
    # Prefer a uv already on PATH (winget/scoop/pipx/standalone installer).
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) { return $uv.Source }
    throw "uv was not found on PATH. Install it, then re-run: winget install --id=astral-sh.uv -e  (or see https://docs.astral.sh/uv/getting-started/installation/)"
}

function Invoke-Native {
    # Run an external command and surface a non-zero exit code as a failure,
    # so a broken step stops the chain (make-style).
    param([Parameter(Mandatory)][string]$Exe, [string[]]$CmdArgs)
    & $Exe @CmdArgs
    if ($LASTEXITCODE -ne 0) {
        throw "command failed (exit $LASTEXITCODE): $Exe $($CmdArgs -join ' ')"
    }
}

function Ensure-Venv {
    if (-not (Test-Path $VenvPy)) {
        Write-Host "-> venv missing; creating it first" -ForegroundColor Yellow
        Invoke-Venv
    }
}

# ---- Targets ----------------------------------------------------------------

function Invoke-Help {
    Write-Host ""
    Write-Host "  StemGen - Windows task runner" -ForegroundColor Cyan
    Write-Host ""
    $rows = @(
        @('venv',      "uv sync - create/refresh $Venv (runtime + build deps, $Variant torch)"),
        @('lock',      'uv lock - refresh uv.lock'),
        @('run',       'run the app from source'),
        @('test',      'run the unit tests'),
        @('build',     "Nuitka compile -> $Dist\StemGenApp.dist\"),
        @('package',   'build + wrap into a timestamped .msi (WiX)'),
        @('clean',     'remove build artefacts'),
        @('distclean', 'clean + remove venv')
    )
    foreach ($r in $rows) {
        Write-Host ("  {0,-12}" -f $r[0]) -ForegroundColor Green -NoNewline
        Write-Host $r[1]
    }
    Write-Host ""
    Write-Host "  usage:  make <target>   or   .\make.ps1 <target> [-Variant cpu|cuda]" -ForegroundColor DarkGray
    Write-Host ""
}

function Invoke-Venv {
    $uv = Resolve-Uv
    # UV_PROJECT_ENVIRONMENT points uv at this variant's venv; --extra
    # $Variant selects its torch (the cpu / cuda extras conflict in
    # pyproject.toml, so exactly one torch is ever installed).
    $env:UV_PROJECT_ENVIRONMENT = $Venv
    Invoke-Native $uv @('sync', '--python', $PythonVersion, '--extra', $Variant, '--extra', 'build', '--extra', 'dev')
}

function Invoke-Lock {
    $uv = Resolve-Uv
    Invoke-Native $uv @('lock', '--python', $PythonVersion)
}

function Invoke-Run {
    Ensure-Venv
    Invoke-Native $VenvPy @($Entry)
}

function Invoke-Test {
    Ensure-Venv
    Invoke-Native $VenvPy @('-m', 'pytest')
}

function Invoke-Build {
    Ensure-Venv
    $env:APP_NAME = $AppName
    $env:ENTRY    = $Entry
    $env:VENV_PY  = $VenvPy
    $env:DIST     = $Dist
    Invoke-Native 'powershell' @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', 'scripts/_build_app.ps1'
    )
}

function Invoke-Package {
    # Compile first (build is the prerequisite), then wrap into the MSI.
    # `make package` is timestamped so dated builds pile up side by side;
    # call _package_windows.ps1 directly (no -Timestamp) for a stable,
    # un-suffixed name.
    Invoke-Build
    $env:APP_NAME = $AppName
    $env:DIST     = $Dist
    $env:MSI_STEM = $MsiStem
    Invoke-Native 'powershell' @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', 'scripts/_package_windows.ps1',
        '-Timestamp'
    )
}

function Invoke-Clean {
    foreach ($p in @('build', 'dist', 'dist.lock', 'dist-cuda', 'dist-cuda.lock', 'dist-nuitka')) {
        if (Test-Path $p) {
            Write-Host "  rm $p"
            Remove-Item $p -Recurse -Force
        }
    }
}

function Invoke-Distclean {
    Invoke-Clean
    foreach ($p in @('.venv', '.venv-cuda', '.uv-bootstrap')) {
        if (Test-Path $p) {
            Write-Host "  rm $p"
            Remove-Item $p -Recurse -Force
        }
    }
}

# ---- Dispatch ---------------------------------------------------------------
switch ($Target.ToLower()) {
    'help'      { Invoke-Help }
    'venv'      { Invoke-Venv }
    'sync'      { Invoke-Venv }   # hidden alias
    'lock'      { Invoke-Lock }
    'run'       { Invoke-Run }
    'test'      { Invoke-Test }
    'build'     { Invoke-Build }
    'package'   { Invoke-Package }
    'clean'     { Invoke-Clean }
    'distclean' { Invoke-Distclean }
    default {
        Write-Host "unknown target: $Target" -ForegroundColor Red
        Invoke-Help
        exit 1
    }
}
