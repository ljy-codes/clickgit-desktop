param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ArtifactsRoot = Join-Path $ProjectRoot "artifacts"
$BuildRoot = Join-Path $ArtifactsRoot "build\windows"
$PublishRoot = Join-Path $ArtifactsRoot "publish\windows-x64"
$PackageRoot = Join-Path $PublishRoot "ClickGit"
$GitRuntime = Join-Path $ProjectRoot "runtime\git"
$GitExecutable = Join-Path $GitRuntime "cmd\git.exe"
$LicenseSource = Join-Path $ProjectRoot "LICENSE"
$NoticesSource = Join-Path $ProjectRoot "THIRD-PARTY-NOTICES.txt"
$PackageRuntime = Join-Path $PackageRoot "runtime\git"
$PackageLicense = Join-Path $PackageRoot "LICENSE"
$PackageNotices = Join-Path $PackageRoot "THIRD-PARTY-NOTICES.txt"
$OriginalPath = $env:PATH

function Assert-ChildPath {
    param(
        [Parameter(Mandatory)]
        [string]$ParentPath,
        [Parameter(Mandatory)]
        [string]$ChildPath
    )

    $NormalizedParent = [IO.Path]::GetFullPath($ParentPath).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $NormalizedChild = [IO.Path]::GetFullPath($ChildPath)
    $RequiredPrefix = $NormalizedParent + [IO.Path]::DirectorySeparatorChar
    if (-not $NormalizedChild.StartsWith(
        $RequiredPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unsafe artifact path outside artifacts: $NormalizedChild"
    }
}

Assert-ChildPath -ParentPath $ArtifactsRoot -ChildPath $BuildRoot
Assert-ChildPath -ParentPath $ArtifactsRoot -ChildPath $PublishRoot
Assert-ChildPath -ParentPath $ArtifactsRoot -ChildPath $PackageRoot
Assert-ChildPath -ParentPath $ArtifactsRoot -ChildPath $PackageRuntime
Assert-ChildPath -ParentPath $ArtifactsRoot -ChildPath $PackageLicense
Assert-ChildPath -ParentPath $ArtifactsRoot -ChildPath $PackageNotices

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & (Join-Path $PSScriptRoot "bootstrap.ps1")
}
if (-not (Test-Path -LiteralPath $GitExecutable)) {
    & (Join-Path $PSScriptRoot "download-portable-git.ps1")
}

Push-Location $ProjectRoot
try {
    if (-not $SkipTests) {
        $env:PYTHONPATH = "src"
        $env:QT_QPA_PLATFORM = "offscreen"
        & $VenvPython -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) {
            throw "Tests failed."
        }
    }
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    $env:PATH = (
        ($OriginalPath -split [IO.Path]::PathSeparator) |
            Where-Object {
                $_ -and
                $_ -notmatch "[\\/]\.cache[\\/]codex-runtimes[\\/]"
            }
    ) -join [IO.Path]::PathSeparator
    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --workpath artifacts\build\windows `
        --distpath artifacts\publish\windows-x64 `
        installer\clickgit.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    foreach ($RequiredSource in @(
        $GitRuntime,
        $GitExecutable,
        $LicenseSource,
        $NoticesSource
    )) {
        if (-not (Test-Path -LiteralPath $RequiredSource)) {
            throw "Required package source was not found: $RequiredSource"
        }
    }
    if (-not (Test-Path -LiteralPath $PackageRoot -PathType Container)) {
        throw "PyInstaller package root was not created: $PackageRoot"
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $PackageRuntime) |
        Out-Null
    Copy-Item -LiteralPath $GitRuntime `
        -Destination $PackageRuntime `
        -Recurse `
        -Force
    Copy-Item -LiteralPath $LicenseSource `
        -Destination $PackageLicense `
        -Force
    Copy-Item -LiteralPath $NoticesSource `
        -Destination $PackageNotices `
        -Force
}
finally {
    $env:PATH = $OriginalPath
    Pop-Location
}

Write-Host "Build completed: $(Join-Path $ProjectRoot 'artifacts\publish\windows-x64\ClickGit\ClickGit.exe')"
