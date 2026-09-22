<#
.SYNOPSIS
    Single-source-of-truth Nuitka build for StemGen on Windows.

.DESCRIPTION
    The Windows counterpart of scripts/_build_app.sh. Produces a standalone
    folder (dist\StemGenApp.dist\) containing StemGenApp.exe plus all bundled
    dependencies and data. We use --mode=standalone (a folder) rather than
    --mode=onefile because the app ships torch (hundreds of MB); onefile would
    re-extract that to %TEMP% on every launch.

    Inputs come from the environment (set by make.ps1 / the Makefile), with
    sensible fallbacks so the script also runs standalone:
        APP_NAME   e.g. "StemGen"
        ENTRY      e.g. src/StemGenApp.py
        VENV_PY    e.g. .venv\Scripts\python.exe
        DIST       e.g. dist

    NOTE: ASCII-only on purpose - Windows PowerShell 5.1 corrupts non-ASCII
    glyphs in BOM-less .ps1 files, which breaks parsing.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---- Inputs -----------------------------------------------------------------
function Get-EnvOr {
    param([string]$Name, [string]$Default)
    $v = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrEmpty($v)) { return $Default }
    return $v
}

$AppName = Get-EnvOr 'APP_NAME' 'StemGen'
$Entry   = Get-EnvOr 'ENTRY'    'src/StemGenApp.py'
$VenvPy  = Get-EnvOr 'VENV_PY'  '.venv\Scripts\python.exe'
$Dist    = Get-EnvOr 'DIST'     'dist'

# Run from the repo root (parent of scripts\).
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

if (-not (Test-Path $VenvPy)) {
    throw "venv python not found at $VenvPy - run 'make venv' first"
}

$EntryStem = [System.IO.Path]::GetFileNameWithoutExtension($Entry)  # StemGenApp
# Build output keeps Nuitka's natural ".dist" folder name (StemGenApp.dist)
# so the WiX harvester in scripts/_package_windows.ps1 can glob it directly.
# The macOS build renames to "StemGen.app"; on Windows the on-disk folder
# stays as-is and the product name only drives the MSI / shortcuts.
$Bundle    = Join-Path $Dist "$EntryStem.dist"
$Lock      = "$Dist.lock"

# ---- Build mutex ------------------------------------------------------------
# Directory creation is atomic: either we make the lock dir or someone else
# holds it. Mirrors the mkdir mutex in _build_app.sh so a backgrounded build
# and a manual one can't race on the dist tree.
if (Test-Path $Lock) {
    $otherPid = (Get-Content (Join-Path $Lock 'pid') -ErrorAction SilentlyContinue) -as [int]
    if (-not $otherPid) {
        throw "a build lock exists but records no pid (another build may be starting). If you are SURE none is running: Remove-Item -Recurse -Force '$Lock'"
    }
    if ([bool](Get-Process -Id $otherPid -ErrorAction SilentlyContinue)) {
        throw "another Nuitka build is in progress (pid $otherPid). Wait for it, or: Stop-Process -Id $otherPid; Remove-Item -Recurse -Force $Lock"
    }
    Write-Host "  removing stale lock from dead pid $otherPid"
    Remove-Item -Recurse -Force $Lock
}
New-Item -ItemType Directory -Path $Lock | Out-Null
$PID | Out-File -FilePath (Join-Path $Lock 'pid') -Encoding ascii

try {
    # ---- Wipe stale outputs ------------------------------------------------
    if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
    New-Item -ItemType Directory -Path $Dist -Force | Out-Null

    # ---- Nuitka flags ------------------------------------------------------
    # Mirrors _build_app.sh, minus the macOS-specific flags (--macos-*) and
    # plus the Windows ones (icon, windowed GUI subsystem, version metadata).
    # The same demucs / PyQt5 / dead-weight-exclusion notes apply on both
    # platforms - see the comment block in _build_app.sh.
    $flags = @(
        '--mode=standalone'
        '--enable-plugin=pyqt5'
        '--windows-icon-from-ico=assets/icons/StemGen.ico'
        '--windows-console-mode=disable'
        "--company-name=$AppName"
        "--product-name=$AppName"
        "--file-description=$AppName"
        '--product-version=0.2.0'
        '--file-version=0.2.0'
        '--include-package=demucs'
        '--include-package-data=demucs'
        '--include-package=julius'
        '--include-package=einops'
        '--include-package=lameenc'
        '--include-package=mutagen'
        # demucs never calls torch.jit; make Nuitka's standalone default
        # explicit so the options-nanny plugin stops asking.
        '--module-parameter=torch-disable-jit=yes'
        '--nofollow-import-to=einops.tests'
        # torch only reaches sympy / jinja2 / _dynamo / _inductor through
        # torch.compile, which demucs never uses (verified with the imports
        # blocked). See _build_app.sh.
        '--nofollow-import-to=sympy'
        '--nofollow-import-to=jinja2'
        '--nofollow-import-to=torch._dynamo'
        '--nofollow-import-to=torch._inductor'
        '--nofollow-import-to=xformers'
        '--nofollow-import-to=triton'
        '--nofollow-import-to=pandas'
        '--nofollow-import-to=matplotlib'
        '--nofollow-import-to=IPython'
        '--nofollow-import-to=jupyter'
        '--nofollow-import-to=PIL'
        '--nofollow-import-to=tkinter'
        '--nofollow-import-to=tensorflow'
        '--nofollow-import-to=jax'
        '--nofollow-import-to=flax'
        '--nofollow-import-to=sklearn'
        '--nofollow-import-to=transformers'
        '--nofollow-import-to=huggingface_hub'
        '--nofollow-import-to=onnx'
        '--nofollow-import-to=onnxruntime'
        '--nofollow-import-to=PyQt5.QtSql'
        '--nofollow-import-to=PyQt5.QtNetwork'
        '--nofollow-import-to=PyQt5.QtWebEngineCore'
        '--nofollow-import-to=PyQt5.QtWebEngineWidgets'
        '--nofollow-import-to=PyQt5.QtWebEngine'
        '--nofollow-import-to=PyQt5.QtMultimedia'
        '--nofollow-import-to=PyQt5.QtMultimediaWidgets'
        '--nofollow-import-to=PyQt5.QtBluetooth'
        '--nofollow-import-to=PyQt5.QtSensors'
        '--nofollow-import-to=PyQt5.QtPositioning'
        '--nofollow-import-to=PyQt5.QtLocation'
        '--nofollow-import-to=PyQt5.QtRemoteObjects'
        '--nofollow-import-to=PyQt5.QtDesigner'
        '--nofollow-import-to=PyQt5.QtQml'
        '--nofollow-import-to=PyQt5.QtQuick'
        '--nofollow-import-to=PyQt5.QtQuickWidgets'
        '--nofollow-import-to=PyQt5.QtWebSockets'
        '--nofollow-import-to=PyQt5.QtWebChannel'
        '--nofollow-import-to=PyQt5.QtSerialPort'
        '--nofollow-import-to=PyQt5.QtNfc'
        '--nofollow-import-to=PyQt5.QtXml'
        '--nofollow-import-to=PyQt5.QtXmlPatterns'
        '--nofollow-import-to=PyQt5.QtTest'
        '--nofollow-import-to=PyQt5.QtHelp'
        '--nofollow-import-to=PyQt5.QtOpenGL'
        '--nofollow-import-to=PyQt5.QtPrintSupport'
        '--nofollow-import-to=PyQt5.QtSvg'
        '--nofollow-import-to=PyQt5.QtDBus'
        '--no-deployment-flag=excluded-module-usage'
        # torch/bin must stay: torch.__init__ refuses to import without
        # bin/torch_shm_manager. include/ is header payload only.
        '--noinclude-data-files=torch/include/*'
        # GPAC ships as a data dir with its layout intact so mp4box.exe finds
        # its DLLs next to it. runtime.mp4box_path() resolves it relative to
        # the launcher.
        '--include-data-dir=GPAC_win=GPAC_win'
        '--include-data-files=LICENSE=LICENSE'
        "--output-dir=$Dist"
        '--remove-output'
        '--assume-yes-for-downloads'
    )

    # ---- Compile -----------------------------------------------------------
    Write-Host ">> Nuitka build -> $Bundle" -ForegroundColor Cyan
    & $VenvPy -m nuitka @flags $Entry
    if ($LASTEXITCODE -ne 0) { throw "Nuitka exited with code $LASTEXITCODE" }

    if (-not (Test-Path $Bundle)) {
        throw "Nuitka did not produce $Bundle (expected $EntryStem.dist in $Dist)"
    }

    $size = (Get-ChildItem -Recurse $Bundle | Measure-Object -Property Length -Sum).Sum
    $sizeMb = [math]::Round($size / 1MB, 1)
    Write-Host "OK: $Bundle  ($sizeMb MB)" -ForegroundColor Green
    Write-Host "  exe: $(Join-Path $Bundle "$EntryStem.exe")"
}
finally {
    # Remove the lock only if this process still owns it - deleting a lock
    # another instance has since (re)claimed would leave that build unprotected.
    $lockPid = (Get-Content (Join-Path $Lock 'pid') -ErrorAction SilentlyContinue) -as [int]
    if ($lockPid -eq $PID) { Remove-Item -Recurse -Force $Lock }
}
