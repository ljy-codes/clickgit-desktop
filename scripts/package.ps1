param(
    [ValidatePattern("^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]
    [string]$Version = "0.2.0",
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

function Remove-FinalPackageOutputs {
    param(
        [Parameter(Mandatory)]
        [string]$ArtifactsRoot,
        [Parameter(Mandatory)]
        [string[]]$OutputPaths
    )

    $CleanupErrors = @()
    foreach ($OutputPath in $OutputPaths) {
        try {
            $ValidatedOutput = Assert-ChildPath `
                -ParentPath $ArtifactsRoot `
                -ChildPath $OutputPath
            if (Test-Path -LiteralPath $ValidatedOutput) {
                Assert-NoReparsePoint `
                    -TrustedRoot $ArtifactsRoot `
                    -Path $ValidatedOutput | Out-Null
                Remove-Item -LiteralPath $ValidatedOutput -Force
            }
        }
        catch {
            $CleanupErrors += $_
        }
    }
    if ($CleanupErrors.Count -gt 0) {
        $Messages = $CleanupErrors |
            ForEach-Object { $_.Exception.Message }
        throw "Failed to clear final package outputs: $($Messages -join '; ')"
    }
}

function Get-Sha256Digest {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $Stream = [IO.File]::OpenRead($Path)
    $Algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $HashBytes = $Algorithm.ComputeHash($Stream)
        return -join ($HashBytes | ForEach-Object {
            $_.ToString("x2")
        })
    }
    finally {
        $Algorithm.Dispose()
        $Stream.Dispose()
    }
}

$ProjectRoot = Get-NormalizedPath $ProjectRoot
$ProjectVolumeRoot = [IO.Path]::GetPathRoot($ProjectRoot)
Assert-NoReparsePoint `
    -TrustedRoot $ProjectVolumeRoot `
    -Path $ProjectRoot | Out-Null
$ArtifactsRoot = Get-NormalizedPath (
    Join-Path $ProjectRoot "artifacts"
)
Assert-NoReparsePoint `
    -TrustedRoot $ProjectRoot `
    -Path $ArtifactsRoot | Out-Null
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
foreach ($ProtectedArtifactPath in @(
    $ApplicationRoot,
    $PackageOutputRoot,
    $InstallerOutputRoot,
    $StagingRoot
)) {
    Assert-NoReparsePoint `
        -TrustedRoot $ArtifactsRoot `
        -Path $ProtectedArtifactPath | Out-Null
}

$BuildScript = Join-Path $ProjectRoot "scripts\build.ps1"
$LicenseVerifier = Join-Path $ProjectRoot "scripts\verify_licenses.py"
$ValidationPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $ValidationPython -PathType Leaf)) {
    $ValidationPython = Get-Command "python" -ErrorAction Stop |
        Select-Object -ExpandProperty Source -First 1
}
if (-not $VerifyScript) {
    $VerifyScript = Join-Path $ProjectRoot "scripts\verify-package.ps1"
}
$VerifyScript = Get-NormalizedPath $VerifyScript
$InstallerScript = Join-Path $ProjectRoot "installer\ClickGit.iss"
$PortableName = "ClickGit-Windows-x64-Portable.zip"
$InstallerName = "ClickGit-Windows-x64-Setup.exe"
$BuildManifestName = "ClickGit-Windows-x64-MANIFEST.json"
$StagedPortable = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $StagingRoot $PortableName)
$StagedInstaller = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $StagingRoot $InstallerName)
$StagedBuildManifest = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $StagingRoot $BuildManifestName)
$PortableOutput = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $PackageOutputRoot $PortableName)
$InstallerOutput = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $InstallerOutputRoot $InstallerName)
$BuildManifestOutput = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $PackageOutputRoot $BuildManifestName)
$FinalOutputs = @(
    $PortableOutput,
    $InstallerOutput,
    $BuildManifestOutput
)
$InstalledFinalOutputs = @()
$BackupOutputs = @{}

try {
    foreach ($RequiredScript in @(
        $VerifyScript,
        $InstallerScript,
        $LicenseVerifier
    )) {
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
    & $ValidationPython $LicenseVerifier `
        --project-root $ProjectRoot `
        --package-root $ApplicationRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged third-party license verification failed."
    }

    foreach ($RequiredPackagePath in @(
        (Join-Path $ApplicationRoot "ClickGit.exe"),
        (Join-Path $ApplicationRoot "runtime\git\cmd\git.exe"),
        (Join-Path $ApplicationRoot "LICENSE"),
        (Join-Path $ApplicationRoot "THIRD-PARTY-NOTICES.txt"),
        (Join-Path $ApplicationRoot "licenses\LICENSE-MANIFEST.json")
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
        Assert-NoReparseTree `
            -TrustedRoot $ArtifactsRoot `
            -Path $ValidatedStagingRoot | Out-Null
        Remove-Item -LiteralPath $ValidatedStagingRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $StagingRoot | Out-Null

    Assert-NoReparseTree `
        -TrustedRoot $ArtifactsRoot `
        -Path $ApplicationRoot | Out-Null
    Compress-Archive `
        -LiteralPath $ApplicationRoot `
        -DestinationPath $StagedPortable `
        -CompressionLevel Optimal

    & $IsccPath `
        "/DAppVersion=$Version" `
        "/DSourceRoot=$ProjectRoot" `
        "/DSourceDir=$ApplicationRoot" `
        "/DOutputDir=$StagingRoot" `
        $InstallerScript
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
    foreach ($StagedProduct in @($StagedPortable, $StagedInstaller)) {
        if (-not (Test-Path -LiteralPath $StagedProduct -PathType Leaf)) {
            throw "Packaging did not create the expected product: $StagedProduct"
        }
    }
    $BuildManifest = [ordered]@{
        schema_version = 1
        version = $Version
        artifacts = [ordered]@{
            $InstallerName = Get-Sha256Digest -Path $StagedInstaller
            $PortableName = Get-Sha256Digest -Path $StagedPortable
        }
    }
    $BuildManifest |
        ConvertTo-Json -Depth 4 |
        Set-Content `
            -LiteralPath $StagedBuildManifest `
            -Encoding UTF8
    if (-not (Test-Path -LiteralPath $StagedBuildManifest -PathType Leaf)) {
        throw "Packaging did not create the Windows build manifest."
    }

    New-Item -ItemType Directory -Force -Path @(
        $PackageOutputRoot,
        $InstallerOutputRoot
    ) | Out-Null
    $BackupOutputRoot = Assert-ChildPath `
        -ParentPath $ArtifactsRoot `
        -ChildPath (Join-Path $StagingRoot "backup")
    New-Item -ItemType Directory -Force -Path $BackupOutputRoot | Out-Null
    foreach ($FinalOutput in $FinalOutputs) {
        if (Test-Path -LiteralPath $FinalOutput -PathType Leaf) {
            $BackupPath = Join-Path `
                $BackupOutputRoot `
                ([IO.Path]::GetFileName($FinalOutput))
            Move-Item `
                -LiteralPath $FinalOutput `
                -Destination $BackupPath
            $BackupOutputs[$FinalOutput] = $BackupPath
        }
    }
    foreach ($OutputPair in @(
        @($StagedPortable, $PortableOutput),
        @($StagedInstaller, $InstallerOutput),
        @($StagedBuildManifest, $BuildManifestOutput)
    )) {
        Move-Item `
            -LiteralPath $OutputPair[0] `
            -Destination $OutputPair[1]
        $InstalledFinalOutputs += $OutputPair[1]
    }
}
catch {
    $PackagingError = $_
    $RollbackErrors = @()
    if ($InstalledFinalOutputs.Count -gt 0) {
        try {
            Remove-FinalPackageOutputs `
                -ArtifactsRoot $ArtifactsRoot `
                -OutputPaths $InstalledFinalOutputs
        }
        catch {
            $RollbackErrors += $_.Exception.Message
        }
    }
    foreach ($FinalOutput in $BackupOutputs.Keys) {
        try {
            if (Test-Path -LiteralPath $BackupOutputs[$FinalOutput]) {
                Move-Item `
                    -LiteralPath $BackupOutputs[$FinalOutput] `
                    -Destination $FinalOutput
            }
        }
        catch {
            $RollbackErrors += $_.Exception.Message
        }
    }
    if ($RollbackErrors.Count -gt 0) {
        throw (
            "Packaging failed: {0} Output rollback also failed: {1}" -f
            $PackagingError.Exception.Message,
            ($RollbackErrors -join "; ")
        )
    }
    throw $PackagingError
}
finally {
    if (Test-Path -LiteralPath $StagingRoot) {
        $ValidatedStagingRoot = Assert-ChildPath `
            -ParentPath $ArtifactsRoot `
            -ChildPath $StagingRoot
        Assert-NoReparseTree `
            -TrustedRoot $ArtifactsRoot `
            -Path $ValidatedStagingRoot | Out-Null
        Remove-Item -LiteralPath $ValidatedStagingRoot -Recurse -Force
    }
}

Write-Host "Portable package: $PortableOutput"
Write-Host "Windows installer: $InstallerOutput"
Write-Host "Windows build manifest: $BuildManifestOutput"
