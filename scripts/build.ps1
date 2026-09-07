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
$LicenseBundleSource = Join-Path $ProjectRoot "docs\licenses\distribution"
$LicenseVerifier = Join-Path $ProjectRoot "scripts\verify_licenses.py"
$PackageRuntime = Join-Path $PackageRoot "runtime\git"
$PackageLicense = Join-Path $PackageRoot "LICENSE"
$PackageNotices = Join-Path $PackageRoot "THIRD-PARTY-NOTICES.txt"
$PackageLicenses = Join-Path $PackageRoot "licenses"
$OriginalPathExists = Test-Path -LiteralPath Env:PATH
$OriginalPythonPathExists = Test-Path -LiteralPath Env:PYTHONPATH
$OriginalQtPlatformExists = Test-Path -LiteralPath Env:QT_QPA_PLATFORM
$OriginalPath = $env:PATH
$OriginalPythonPath = if ($OriginalPythonPathExists) {
    $env:PYTHONPATH
}
else {
    $null
}
$OriginalQtPlatform = if ($OriginalQtPlatformExists) {
    $env:QT_QPA_PLATFORM
}
else {
    $null
}
$LocationPushed = $false

function Get-NormalizedPath {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $FullPath = [IO.Path]::GetFullPath($Path)
    $PathRoot = [IO.Path]::GetPathRoot($FullPath)
    if ($FullPath.Equals(
        $PathRoot,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        return $PathRoot
    }
    return $FullPath.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
}

function Assert-ChildPath {
    param(
        [Parameter(Mandatory)]
        [string]$ParentPath,
        [Parameter(Mandatory)]
        [string]$ChildPath
    )

    $NormalizedParent = Get-NormalizedPath $ParentPath
    $NormalizedChild = Get-NormalizedPath $ChildPath
    $RequiredPrefix = $NormalizedParent + [IO.Path]::DirectorySeparatorChar
    if (-not $NormalizedChild.StartsWith(
        $RequiredPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unsafe artifact path outside artifacts: $NormalizedChild"
    }
    return $NormalizedChild
}

function Assert-NoReparsePoint {
    param(
        [Parameter(Mandatory)]
        [string]$TrustedRoot,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $NormalizedRoot = Get-NormalizedPath $TrustedRoot
    $NormalizedPath = Get-NormalizedPath $Path
    $RequiredPrefix = $NormalizedRoot
    if (-not $RequiredPrefix.EndsWith(
        [IO.Path]::DirectorySeparatorChar.ToString()
    )) {
        $RequiredPrefix += [IO.Path]::DirectorySeparatorChar
    }
    $IsTrustedRoot = $NormalizedPath.Equals(
        $NormalizedRoot,
        [StringComparison]::OrdinalIgnoreCase
    )
    if (
        -not $IsTrustedRoot -and
        -not $NormalizedPath.StartsWith(
            $RequiredPrefix,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "Unsafe reparse-point check: $NormalizedPath"
    }

    $CurrentPath = $NormalizedRoot
    $RelativePath = if ($IsTrustedRoot) {
        ""
    }
    else {
        $NormalizedPath.Substring($NormalizedRoot.Length).TrimStart(
            [IO.Path]::DirectorySeparatorChar,
            [IO.Path]::AltDirectorySeparatorChar
        )
    }
    $PathParts = if ($RelativePath) {
        $RelativePath.Split(
            [char[]]@(
                [IO.Path]::DirectorySeparatorChar,
                [IO.Path]::AltDirectorySeparatorChar
            ),
            [StringSplitOptions]::RemoveEmptyEntries
        )
    }
    else {
        @()
    }
    foreach ($PathPart in @("") + $PathParts) {
        if ($PathPart) {
            $CurrentPath = Join-Path $CurrentPath $PathPart
        }
        if (-not (Test-Path -LiteralPath $CurrentPath)) {
            break
        }
        $CurrentItem = Get-Item -LiteralPath $CurrentPath -Force
        if (
            ($CurrentItem.Attributes -band
                [IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "Reparse point is not allowed: $CurrentPath"
        }
    }
    return $NormalizedPath
}

function Assert-NoReparseTree {
    param(
        [Parameter(Mandatory)]
        [string]$TrustedRoot,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $ValidatedPath = Assert-NoReparsePoint `
        -TrustedRoot $TrustedRoot `
        -Path $Path
    if (-not (Test-Path -LiteralPath $ValidatedPath -PathType Container)) {
        return $ValidatedPath
    }
    $PendingPaths = New-Object "Collections.Generic.Queue[string]"
    $PendingPaths.Enqueue($ValidatedPath)
    while ($PendingPaths.Count -gt 0) {
        $CurrentDirectory = $PendingPaths.Dequeue()
        foreach ($ChildItem in Get-ChildItem `
            -LiteralPath $CurrentDirectory `
            -Force) {
            if (
                ($ChildItem.Attributes -band
                    [IO.FileAttributes]::ReparsePoint) -ne 0
            ) {
                throw "Reparse point is not allowed: $($ChildItem.FullName)"
            }
            if ($ChildItem.PSIsContainer) {
                $PendingPaths.Enqueue($ChildItem.FullName)
            }
        }
    }
    return $ValidatedPath
}

try {
    $ProjectVolumeRoot = [IO.Path]::GetPathRoot($ProjectRoot)
    Assert-NoReparsePoint `
        -TrustedRoot $ProjectVolumeRoot `
        -Path $ProjectRoot | Out-Null
    Assert-NoReparsePoint `
        -TrustedRoot $ProjectRoot `
        -Path $ArtifactsRoot | Out-Null
    $ValidatedBuildRoot = Assert-ChildPath `
        -ParentPath $ArtifactsRoot `
        -ChildPath $BuildRoot
    $ValidatedPublishRoot = Assert-ChildPath `
        -ParentPath $ArtifactsRoot `
        -ChildPath $PublishRoot
    $ValidatedPackageRoot = Assert-ChildPath `
        -ParentPath $ArtifactsRoot `
        -ChildPath $PackageRoot
    foreach ($ProtectedArtifactPath in @(
        $ValidatedBuildRoot,
        $ValidatedPublishRoot,
        $ValidatedPackageRoot
    )) {
        Assert-NoReparsePoint `
            -TrustedRoot $ArtifactsRoot `
            -Path $ProtectedArtifactPath | Out-Null
    }
    Assert-ChildPath `
        -ParentPath $ArtifactsRoot `
        -ChildPath $PackageRuntime | Out-Null
    Assert-ChildPath `
        -ParentPath $ArtifactsRoot `
        -ChildPath $PackageLicense | Out-Null
    Assert-ChildPath `
        -ParentPath $ArtifactsRoot `
        -ChildPath $PackageNotices | Out-Null
    Assert-ChildPath `
        -ParentPath $ArtifactsRoot `
        -ChildPath $PackageLicenses | Out-Null

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        & (Join-Path $PSScriptRoot "bootstrap.ps1")
    }
    $ExpectedGitVersion = "git version 2.55.0.windows.3"
    $ActualGitVersion = if (Test-Path -LiteralPath $GitExecutable) {
        (& $GitExecutable --version)
    }
    else {
        ""
    }
    if ($ActualGitVersion -ne $ExpectedGitVersion) {
        & (Join-Path $PSScriptRoot "download-portable-git.ps1")
    }
    & $VenvPython $LicenseVerifier `
        --project-root $ProjectRoot `
        --python-executable $VenvPython `
        --git-executable $GitExecutable
    if ($LASTEXITCODE -ne 0) {
        throw "Third-party license verification failed."
    }

    Push-Location $ProjectRoot
    $LocationPushed = $true

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

    foreach ($CleanTarget in @(
        $ValidatedBuildRoot,
        $ValidatedPackageRoot
    )) {
        if (Test-Path -LiteralPath $CleanTarget) {
            Assert-NoReparseTree `
                -TrustedRoot $ArtifactsRoot `
                -Path $CleanTarget | Out-Null
            Remove-Item -LiteralPath $CleanTarget -Recurse -Force
        }
    }

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
        $NoticesSource,
        $LicenseVerifier,
        (Join-Path $LicenseBundleSource "LICENSE-MANIFEST.json")
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
    Assert-NoReparseTree `
        -TrustedRoot $ProjectRoot `
        -Path $GitRuntime | Out-Null
    Assert-NoReparseTree `
        -TrustedRoot $ProjectRoot `
        -Path $LicenseBundleSource | Out-Null
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
    Copy-Item -LiteralPath $LicenseBundleSource `
        -Destination $PackageLicenses `
        -Recurse `
        -Force
    & $VenvPython $LicenseVerifier `
        --project-root $ProjectRoot `
        --package-root $PackageRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged third-party license verification failed."
    }
}
finally {
    if ($OriginalPathExists) {
        $env:PATH = $OriginalPath
    }
    else {
        Remove-Item -LiteralPath Env:PATH -ErrorAction SilentlyContinue
    }
    if ($OriginalPythonPathExists) {
        $env:PYTHONPATH = $OriginalPythonPath
    }
    else {
        Remove-Item -LiteralPath Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    if ($OriginalQtPlatformExists) {
        $env:QT_QPA_PLATFORM = $OriginalQtPlatform
    }
    else {
        Remove-Item `
            -LiteralPath Env:QT_QPA_PLATFORM `
            -ErrorAction SilentlyContinue
    }
    if ($LocationPushed) {
        Pop-Location
    }
}

Write-Host "Build completed: $(Join-Path $ProjectRoot 'artifacts\publish\windows-x64\ClickGit\ClickGit.exe')"
