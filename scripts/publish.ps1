param(
    [ValidatePattern("^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]
    [string]$Version = "0.1.0",
    [switch]$SkipPackage,
    [string]$ProjectRoot = (Join-Path $PSScriptRoot ".."),
    [string]$OuterRoot
)

$ErrorActionPreference = "Stop"

# Keep this user-facing delivery name in the source contract:
# ClickGit-安装包.exe

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
    $RequiredPrefix = $NormalizedParent
    if (-not $RequiredPrefix.EndsWith(
        [IO.Path]::DirectorySeparatorChar.ToString()
    )) {
        $RequiredPrefix += [IO.Path]::DirectorySeparatorChar
    }
    if (-not $NormalizedChild.StartsWith(
        $RequiredPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unsafe path outside '$NormalizedParent': $NormalizedChild"
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
        throw (
            "Unsafe reparse-point check outside trusted root " +
            "'$NormalizedRoot': $NormalizedPath"
        )
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
    $PathParts = @()
    if ($RelativePath) {
        $PathParts = $RelativePath.Split(
            [char[]]@(
                [IO.Path]::DirectorySeparatorChar,
                [IO.Path]::AltDirectorySeparatorChar
            ),
            [StringSplitOptions]::RemoveEmptyEntries
        )
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
    if (-not (Test-Path -LiteralPath $ValidatedPath)) {
        return $ValidatedPath
    }
    $RootItem = Get-Item -LiteralPath $ValidatedPath -Force
    if (-not $RootItem.PSIsContainer) {
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

function Assert-RequiredFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required release file was not found: $Path"
    }
    if ((Get-Item -LiteralPath $Path).Length -le 0) {
        throw "Required release file is empty: $Path"
    }
}

function Copy-CheckedFile {
    param(
        [Parameter(Mandatory)]
        [string]$SourceTrustedRoot,
        [Parameter(Mandatory)]
        [string]$Source,
        [Parameter(Mandatory)]
        [string]$DestinationTrustedRoot,
        [Parameter(Mandatory)]
        [string]$Destination
    )

    $ValidatedSource = Assert-NoReparsePoint `
        -TrustedRoot $SourceTrustedRoot `
        -Path $Source
    $ValidatedDestination = Assert-NoReparsePoint `
        -TrustedRoot $DestinationTrustedRoot `
        -Path $Destination
    Assert-RequiredFile $ValidatedSource
    Copy-Item `
        -LiteralPath $ValidatedSource `
        -Destination $ValidatedDestination `
        -Force
}

function Remove-CheckedItem {
    param(
        [Parameter(Mandatory)]
        [string]$ParentPath,
        [Parameter(Mandatory)]
        [string]$Path,
        [switch]$Recurse
    )

    $ValidatedPath = Assert-ChildPath `
        -ParentPath $ParentPath `
        -ChildPath $Path
    if (Test-Path -LiteralPath $ValidatedPath) {
        if ($Recurse) {
            Assert-NoReparseTree `
                -TrustedRoot $ParentPath `
                -Path $ValidatedPath | Out-Null
        }
        else {
            Assert-NoReparsePoint `
                -TrustedRoot $ParentPath `
                -Path $ValidatedPath | Out-Null
        }
        Remove-Item `
            -LiteralPath $ValidatedPath `
            -Recurse:$Recurse `
            -Force
    }
}

function Move-CheckedItem {
    param(
        [Parameter(Mandatory)]
        [string]$SourceParent,
        [Parameter(Mandatory)]
        [string]$Source,
        [Parameter(Mandatory)]
        [string]$DestinationParent,
        [Parameter(Mandatory)]
        [string]$Destination
    )

    $ValidatedSource = Assert-ChildPath `
        -ParentPath $SourceParent `
        -ChildPath $Source
    $ValidatedDestination = Assert-ChildPath `
        -ParentPath $DestinationParent `
        -ChildPath $Destination
    Assert-NoReparseTree `
        -TrustedRoot $SourceParent `
        -Path $ValidatedSource | Out-Null
    Assert-NoReparseTree `
        -TrustedRoot $DestinationParent `
        -Path $ValidatedDestination | Out-Null
    Move-Item `
        -LiteralPath $ValidatedSource `
        -Destination $ValidatedDestination `
        -Force
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

function Write-Sha256Manifest {
    param(
        [Parameter(Mandatory)]
        [string]$DeliveryPath
    )

    $ManifestPath = Join-Path $DeliveryPath "SHA256SUMS.txt"
    $Lines = Get-ChildItem -LiteralPath $DeliveryPath -Force |
        Where-Object {
            $_.PSIsContainer -eq $false -and
            $_.Name -ne "SHA256SUMS.txt"
        } |
        Sort-Object Name |
        ForEach-Object {
            $Digest = Get-Sha256Digest -Path $_.FullName
            "$Digest  $($_.Name)"
        }
    Set-Content `
        -LiteralPath $ManifestPath `
        -Value $Lines `
        -Encoding UTF8
}

function Assert-Sha256Manifest {
    param(
        [Parameter(Mandatory)]
        [string]$DeliveryPath
    )

    $ManifestPath = Join-Path $DeliveryPath "SHA256SUMS.txt"
    Assert-RequiredFile $ManifestPath
    $ExpectedNames = @{}
    foreach ($Line in Get-Content -LiteralPath $ManifestPath -Encoding UTF8) {
        if (-not $Line.Trim()) {
            continue
        }
        if ($Line -notmatch "^([0-9a-fA-F]{64})\s+[*]?(.+)$") {
            throw "Invalid SHA-256 manifest line: $Line"
        }
        $Digest = $Matches[1].ToLowerInvariant()
        $FileName = $Matches[2]
        if ($ExpectedNames.ContainsKey($FileName)) {
            throw "Duplicate SHA-256 entry: $FileName"
        }
        $ExpectedNames[$FileName] = $Digest
    }

    $DeliveryFiles = @(
        Get-ChildItem -LiteralPath $DeliveryPath -Force |
            Where-Object {
                $_.PSIsContainer -eq $false -and
                $_.Name -ne "SHA256SUMS.txt"
            }
    )
    if ($ExpectedNames.Count -ne $DeliveryFiles.Count) {
        throw "SHA-256 manifest does not match the staged file count."
    }
    foreach ($File in $DeliveryFiles) {
        if (-not $ExpectedNames.ContainsKey($File.Name)) {
            throw "SHA-256 manifest is missing: $($File.Name)"
        }
        $ActualDigest = Get-Sha256Digest -Path $File.FullName
        if ($ActualDigest -ne $ExpectedNames[$File.Name]) {
            throw "SHA-256 mismatch: $($File.Name)"
        }
    }
}

$ProjectRoot = Get-NormalizedPath $ProjectRoot
$ProjectVolumeRoot = [IO.Path]::GetPathRoot($ProjectRoot)
Assert-NoReparsePoint `
    -TrustedRoot $ProjectVolumeRoot `
    -Path $ProjectRoot | Out-Null
if (-not $OuterRoot) {
    $OuterRoot = Split-Path -Parent $ProjectRoot
}
$OuterRoot = Get-NormalizedPath $OuterRoot
$OuterVolumeRoot = [IO.Path]::GetPathRoot($OuterRoot)
Assert-NoReparsePoint `
    -TrustedRoot $OuterVolumeRoot `
    -Path $OuterRoot | Out-Null
$ExpectedOuterRoot = Get-NormalizedPath (Split-Path -Parent $ProjectRoot)
if (-not $OuterRoot.Equals(
    $ExpectedOuterRoot,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw (
        "OuterRoot must be the direct parent of ProjectRoot. " +
        "Expected '$ExpectedOuterRoot', received '$OuterRoot'."
    )
}

$DeliveryDirectoryName = -join @(
    [char]0x4EA4,
    [char]0x4ED8,
    [char]0x4EA7,
    [char]0x54C1
)
$InstallText = -join @(
    [char]0x5B89,
    [char]0x88C5
)
$PackageText = -join @(
    [char]0x5305
)
$GuideText = -join @(
    [char]0x8BF4,
    [char]0x660E
)
$ProductText = -join @(
    [char]0x4EA7,
    [char]0x54C1
)
$IntroductionText = -join @(
    [char]0x4ECB,
    [char]0x7ECD
)
$InstallerCopyName = "ClickGit-$InstallText$PackageText.exe"
$InstallGuideName = "$InstallText$GuideText.html"
$ProductIntroName = "$ProductText$IntroductionText.html"

$ArtifactsRoot = Assert-ChildPath `
    -ParentPath $ProjectRoot `
    -ChildPath (Join-Path $ProjectRoot "artifacts")
Assert-NoReparsePoint `
    -TrustedRoot $ProjectRoot `
    -Path $ArtifactsRoot | Out-Null
$StagingRoot = Assert-ChildPath `
    -ParentPath $ArtifactsRoot `
    -ChildPath (Join-Path $ArtifactsRoot "delivery-staging-$PID")
$StagedDelivery = Assert-ChildPath `
    -ParentPath $StagingRoot `
    -ChildPath (Join-Path $StagingRoot $DeliveryDirectoryName)
$StagedOuterFiles = Assert-ChildPath `
    -ParentPath $StagingRoot `
    -ChildPath (Join-Path $StagingRoot "outer")
$BackupRoot = Assert-ChildPath `
    -ParentPath $StagingRoot `
    -ChildPath (Join-Path $StagingRoot "backup")
$BackupDelivery = Assert-ChildPath `
    -ParentPath $BackupRoot `
    -ChildPath (Join-Path $BackupRoot $DeliveryDirectoryName)
$BackupOuterFiles = Assert-ChildPath `
    -ParentPath $BackupRoot `
    -ChildPath (Join-Path $BackupRoot "outer")
foreach ($ProtectedArtifactsPath in @(
    $StagingRoot,
    $StagedDelivery,
    $StagedOuterFiles,
    $BackupRoot,
    $BackupDelivery,
    $BackupOuterFiles
)) {
    Assert-NoReparsePoint `
        -TrustedRoot $ArtifactsRoot `
        -Path $ProtectedArtifactsPath | Out-Null
}

$DeliveryRoot = Assert-ChildPath `
    -ParentPath $OuterRoot `
    -ChildPath (Join-Path $OuterRoot $DeliveryDirectoryName)
Assert-NoReparsePoint `
    -TrustedRoot $OuterRoot `
    -Path $DeliveryRoot | Out-Null
$PackageScript = Join-Path $ProjectRoot "scripts\package.ps1"
$InstallerSource = Join-Path (
    Join-Path $ProjectRoot "artifacts\installer"
) "ClickGit-Windows-x64-Setup.exe"
$PackageSourceRoot = Join-Path $ProjectRoot "artifacts\package"
$PortableSource = Join-Path (
    $PackageSourceRoot
) "ClickGit-Windows-x64-Portable.zip"
$InstallGuideSource = Join-Path (
    Join-Path $ProjectRoot "docs\user"
) $InstallGuideName
$ProductIntroSource = Join-Path (
    Join-Path $ProjectRoot "docs\user"
) $ProductIntroName

$InstallerName = "ClickGit-Windows-x64-Setup.exe"
$PortableName = "ClickGit-Windows-x64-Portable.zip"
$MacNames = @(
    "ClickGit-macOS-arm64.zip",
    "ClickGit-macOS-x64.zip"
)
$OuterFileSources = [ordered]@{
    $InstallerCopyName = $InstallerSource
    $InstallGuideName = $InstallGuideSource
    $ProductIntroName = $ProductIntroSource
}
$AllowedDeliveryNames = @(
    $InstallerName,
    $PortableName,
    $MacNames[0],
    $MacNames[1],
    "SHA256SUMS.txt"
)
$BackupOuterNames = @()
$DeliveryBackedUp = $false
$NewDeliveryInstalled = $false
$InstalledOuterNames = @()
$PublishSucceeded = $false

try {
    if (-not $SkipPackage) {
        Assert-RequiredFile $PackageScript
        & $PackageScript `
            -Version $Version `
            -ProjectRoot $ProjectRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Windows packaging failed with exit code $LASTEXITCODE."
        }
    }

    foreach ($RequiredFile in @(
        $InstallerSource,
        $PortableSource,
        $InstallGuideSource,
        $ProductIntroSource
    )) {
        Assert-RequiredFile $RequiredFile
        Assert-NoReparsePoint `
            -TrustedRoot $ProjectRoot `
            -Path $RequiredFile | Out-Null
    }

    if (Test-Path -LiteralPath $StagingRoot) {
        Remove-CheckedItem `
            -ParentPath $ArtifactsRoot `
            -Path $StagingRoot `
            -Recurse
    }
    New-Item -ItemType Directory -Force -Path @(
        $StagedDelivery,
        $StagedOuterFiles,
        $BackupOuterFiles
    ) | Out-Null

    Copy-CheckedFile `
        -SourceTrustedRoot $ProjectRoot `
        -Source $InstallerSource `
        -DestinationTrustedRoot $StagingRoot `
        -Destination (Join-Path $StagedDelivery $InstallerName)
    Copy-CheckedFile `
        -SourceTrustedRoot $ProjectRoot `
        -Source $PortableSource `
        -DestinationTrustedRoot $StagingRoot `
        -Destination (Join-Path $StagedDelivery $PortableName)
    foreach ($MacName in $MacNames) {
        $MacPackageSource = Join-Path $PackageSourceRoot $MacName
        $MacSource = $null
        $MacTrustedRoot = $null
        if (Test-Path -LiteralPath $MacPackageSource -PathType Leaf) {
            $MacSource = $MacPackageSource
            $MacTrustedRoot = $ProjectRoot
        }
        else {
            $ExistingMacSource = Join-Path $DeliveryRoot $MacName
            if (Test-Path -LiteralPath $ExistingMacSource -PathType Leaf) {
                $MacSource = $ExistingMacSource
                $MacTrustedRoot = $OuterRoot
            }
        }
        if ($MacSource) {
            Copy-CheckedFile `
                -SourceTrustedRoot $MacTrustedRoot `
                -Source $MacSource `
                -DestinationTrustedRoot $StagingRoot `
                -Destination (Join-Path $StagedDelivery $MacName)
        }
    }

    $UnexpectedEntries = @(
        Get-ChildItem -LiteralPath $StagedDelivery -Force |
            Where-Object {
                $_.PSIsContainer -or
                $_.Name -notin $AllowedDeliveryNames
            }
    )
    if ($UnexpectedEntries.Count -gt 0) {
        throw (
            "Delivery staging contains unexpected entries: " +
            (($UnexpectedEntries | Select-Object -ExpandProperty Name) -join ", ")
        )
    }
    foreach ($RequiredStagedProduct in @(
        (Join-Path $StagedDelivery $InstallerName),
        (Join-Path $StagedDelivery $PortableName)
    )) {
        Assert-RequiredFile $RequiredStagedProduct
    }

    foreach ($OuterFileName in $OuterFileSources.Keys) {
        Copy-CheckedFile `
            -SourceTrustedRoot $ProjectRoot `
            -Source $OuterFileSources[$OuterFileName] `
            -DestinationTrustedRoot $StagingRoot `
            -Destination (Join-Path $StagedOuterFiles $OuterFileName)
        Assert-RequiredFile (Join-Path $StagedOuterFiles $OuterFileName)
    }
    Write-Sha256Manifest -DeliveryPath $StagedDelivery
    Assert-Sha256Manifest -DeliveryPath $StagedDelivery

    if (Test-Path -LiteralPath $DeliveryRoot) {
        Move-CheckedItem `
            -SourceParent $OuterRoot `
            -Source $DeliveryRoot `
            -DestinationParent $BackupRoot `
            -Destination $BackupDelivery
        $DeliveryBackedUp = $true
    }

    Move-CheckedItem `
        -SourceParent $StagingRoot `
        -Source $StagedDelivery `
        -DestinationParent $OuterRoot `
        -Destination $DeliveryRoot
    $NewDeliveryInstalled = $true

    foreach ($OuterFileName in $OuterFileSources.Keys) {
        $OuterDestination = Assert-ChildPath `
            -ParentPath $OuterRoot `
            -ChildPath (Join-Path $OuterRoot $OuterFileName)
        if (Test-Path -LiteralPath $OuterDestination) {
            $BackupDestination = Join-Path $BackupOuterFiles $OuterFileName
            Move-CheckedItem `
                -SourceParent $OuterRoot `
                -Source $OuterDestination `
                -DestinationParent $BackupRoot `
                -Destination $BackupDestination
            $BackupOuterNames += $OuterFileName
        }
        Move-CheckedItem `
            -SourceParent $StagingRoot `
            -Source (Join-Path $StagedOuterFiles $OuterFileName) `
            -DestinationParent $OuterRoot `
            -Destination $OuterDestination
        $InstalledOuterNames += $OuterFileName
    }

    Assert-Sha256Manifest -DeliveryPath $DeliveryRoot
    $UnexpectedFinalEntries = @(
        Get-ChildItem -LiteralPath $DeliveryRoot -Force |
            Where-Object {
                $_.PSIsContainer -or
                $_.Name -notin $AllowedDeliveryNames
            }
    )
    if ($UnexpectedFinalEntries.Count -gt 0) {
        throw (
            "Final delivery contains unexpected entries: " +
            (($UnexpectedFinalEntries |
                Select-Object -ExpandProperty Name) -join ", ")
        )
    }
    $PublishSucceeded = $true
}
catch {
    $PublishError = $_
    $RollbackErrors = @()

    foreach ($OuterFileName in $InstalledOuterNames) {
        try {
            Remove-CheckedItem `
                -ParentPath $OuterRoot `
                -Path (Join-Path $OuterRoot $OuterFileName)
        }
        catch {
            $RollbackErrors += $_.Exception.Message
        }
    }
    foreach ($OuterFileName in $BackupOuterNames) {
        try {
            $BackupSource = Join-Path $BackupOuterFiles $OuterFileName
            if (Test-Path -LiteralPath $BackupSource) {
                Move-CheckedItem `
                    -SourceParent $BackupRoot `
                    -Source $BackupSource `
                    -DestinationParent $OuterRoot `
                    -Destination (Join-Path $OuterRoot $OuterFileName)
            }
        }
        catch {
            $RollbackErrors += $_.Exception.Message
        }
    }
    if ($NewDeliveryInstalled) {
        try {
            Remove-CheckedItem `
                -ParentPath $OuterRoot `
                -Path $DeliveryRoot `
                -Recurse
        }
        catch {
            $RollbackErrors += $_.Exception.Message
        }
    }
    if ($DeliveryBackedUp) {
        try {
            if (Test-Path -LiteralPath $BackupDelivery) {
                Move-CheckedItem `
                    -SourceParent $BackupRoot `
                    -Source $BackupDelivery `
                    -DestinationParent $OuterRoot `
                    -Destination $DeliveryRoot
            }
        }
        catch {
            $RollbackErrors += $_.Exception.Message
        }
    }

    if ($RollbackErrors.Count -gt 0) {
        throw (
            "Publishing failed: {0} Rollback also failed: {1}" -f
            $PublishError.Exception.Message,
            ($RollbackErrors -join "; ")
        )
    }
    throw $PublishError
}
finally {
    if (Test-Path -LiteralPath $StagingRoot) {
        Remove-CheckedItem `
            -ParentPath $ArtifactsRoot `
            -Path $StagingRoot `
            -Recurse
    }
}

if (-not $PublishSucceeded) {
    throw "Publishing did not complete."
}

Write-Host "Delivery directory: $DeliveryRoot"
Write-Host "Installer copy: $(Join-Path $OuterRoot $InstallerCopyName)"
Write-Host "Install guide: $(Join-Path $OuterRoot $InstallGuideName)"
Write-Host "Product introduction: $(Join-Path $OuterRoot $ProductIntroName)"
