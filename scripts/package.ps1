param(
    [ValidatePattern("^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]
    [string]$Version = "0.1.0",
    [switch]$SkipBuild,
    [string]$ProjectRoot = (Join-Path $PSScriptRoot ".."),
    [string]$VerifyScript,
    [string]$IsccPath
)

$ErrorActionPreference = "Stop"

function Get-NormalizedPath {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    return [IO.Path]::GetFullPath($Path).TrimEnd(
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

function Find-IsccPath {
    $Candidates = @(
        (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Source -First 1),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $Candidate).Path
        }
    }
    throw "Inno Setup 6 ISCC.exe was not found."
}

$ProjectRoot = Get-NormalizedPath $ProjectRoot
$ArtifactsRoot = Get-NormalizedPath (
    Join-Path $ProjectRoot "artifacts"
)
$ApplicationRoot = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $ArtifactsRoot "publish\windows-x64\ClickGit")
$PackageOutputRoot = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $ArtifactsRoot "package")
$InstallerOutputRoot = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $ArtifactsRoot "installer")
$StagingRoot = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $ArtifactsRoot "staging\package-$PID")

$BuildScript = Join-Path $ProjectRoot "scripts\build.ps1"
if (-not $VerifyScript) {
    $VerifyScript = Join-Path $ProjectRoot "scripts\verify-package.ps1"
}
$VerifyScript = Get-NormalizedPath $VerifyScript
$InstallerScript = Join-Path $ProjectRoot "installer\ClickGit.iss"
$PortableName = "ClickGit-Windows-x64-Portable.zip"
$InstallerName = "ClickGit-Windows-x64-Setup.exe"
$StagedPortable = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $StagingRoot $PortableName)
$StagedInstaller = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $StagingRoot $InstallerName)
$PortableOutput = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $PackageOutputRoot $PortableName)
$InstallerOutput = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $InstallerOutputRoot $InstallerName)

try {
    foreach ($RequiredScript in @($VerifyScript, $InstallerScript)) {
        if (-not (Test-Path -LiteralPath $RequiredScript -PathType Leaf)) {
            throw "Required packaging file was not found: $RequiredScript"
        }
    }

    if (-not $SkipBuild) {
        if (-not (Test-Path -LiteralPath $BuildScript -PathType Leaf)) {
            throw "Build script was not found: $BuildScript"
        }
        & $BuildScript
        if ($LASTEXITCODE -ne 0) {
            throw "Windows build failed with exit code $LASTEXITCODE."
        }
    }

    $LASTEXITCODE = 0
    & $VerifyScript `
        -ProjectRoot $ProjectRoot `
        -PackageRoot $ApplicationRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Package verification failed with exit code $LASTEXITCODE."
    }

    foreach ($RequiredPackagePath in @(
        (Join-Path $ApplicationRoot "ClickGit.exe"),
        (Join-Path $ApplicationRoot "runtime\git\cmd\git.exe"),
        (Join-Path $ApplicationRoot "LICENSE"),
        (Join-Path $ApplicationRoot "THIRD-PARTY-NOTICES.txt")
    )) {
        if (-not (Test-Path -LiteralPath $RequiredPackagePath -PathType Leaf)) {
            throw "Required package content was not found: $RequiredPackagePath"
        }
    }

    if (-not $IsccPath) {
        $IsccPath = Find-IsccPath
    }
    $IsccPath = Get-NormalizedPath $IsccPath
    if (-not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
        throw "Inno Setup compiler was not found: $IsccPath"
    }

    if (Test-Path -LiteralPath $StagingRoot) {
        $ValidatedStagingRoot = Assert-ChildPath `
            -ParentPath $ArtifactsRoot `
            -ChildPath $StagingRoot
        Remove-Item -LiteralPath $ValidatedStagingRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $StagingRoot | Out-Null

    Compress-Archive `
        -LiteralPath $ApplicationRoot `
        -DestinationPath $StagedPortable `
        -CompressionLevel Optimal

    & $IsccPath `
        "/DAppVersion=$Version" `
        "/DSourceDir=$ApplicationRoot" `
        "/DOutputDir=$StagingRoot" `
        $InstallerScript
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath $StagedInstaller -PathType Leaf)) {
        throw "Inno Setup did not create the expected installer."
    }

    New-Item -ItemType Directory -Force -Path @(
        $PackageOutputRoot,
        $InstallerOutputRoot
    ) | Out-Null
    Copy-Item -LiteralPath $StagedPortable `
        -Destination $PortableOutput `
        -Force
    Copy-Item -LiteralPath $StagedInstaller `
        -Destination $InstallerOutput `
        -Force
}
finally {
    if (Test-Path -LiteralPath $StagingRoot) {
        $ValidatedStagingRoot = Assert-ChildPath `
            -ParentPath $ArtifactsRoot `
            -ChildPath $StagingRoot
        Remove-Item -LiteralPath $ValidatedStagingRoot -Recurse -Force
    }
}

Write-Host "Portable package: $PortableOutput"
Write-Host "Windows installer: $InstallerOutput"
