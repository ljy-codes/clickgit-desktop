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
        throw "Unsafe path outside '$NormalizedParent': $NormalizedChild"
    }
    return $NormalizedChild
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
if (-not $OuterRoot) {
    $OuterRoot = Split-Path -Parent $ProjectRoot
}
$OuterRoot = Get-NormalizedPath $OuterRoot
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

$DeliveryRoot = Assert-ChildPath `
    -ParentPath $OuterRoot `
    -ChildPath (Join-Path $OuterRoot $DeliveryDirectoryName)
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
$LegacyNames = @("ClickGit", "ClickGit.zip")
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

    if (Test-Path -LiteralPath $DeliveryRoot -PathType Container) {
        foreach ($ExistingEntry in Get-ChildItem `
            -LiteralPath $DeliveryRoot `
            -Force) {
            if (
                $ExistingEntry.Name -in $LegacyNames -or
                $ExistingEntry.Name -eq "SHA256SUMS.txt"
            ) {
                continue
            }
            Copy-Item `
                -LiteralPath $ExistingEntry.FullName `
                -Destination (Join-Path $StagedDelivery $ExistingEntry.Name) `
                -Recurse `
                -Force
        }
    }

    Copy-Item `
        -LiteralPath $InstallerSource `
        -Destination (Join-Path $StagedDelivery $InstallerName) `
        -Force
    Copy-Item `
        -LiteralPath $PortableSource `
        -Destination (Join-Path $StagedDelivery $PortableName) `
        -Force
    foreach ($MacName in $MacNames) {
        $MacPackageSource = Join-Path $PackageSourceRoot $MacName
        if (Test-Path -LiteralPath $MacPackageSource -PathType Leaf) {
            Copy-Item `
                -LiteralPath $MacPackageSource `
                -Destination (Join-Path $StagedDelivery $MacName) `
                -Force
        }
    }

    $UnexpectedDirectories = @(
        Get-ChildItem -LiteralPath $StagedDelivery -Force |
            Where-Object { $_.PSIsContainer }
    )
    if ($UnexpectedDirectories.Count -gt 0) {
        throw (
            "Delivery staging must contain files only: " +
            (($UnexpectedDirectories | Select-Object -ExpandProperty Name) -join ", ")
        )
    }
    foreach ($RequiredStagedProduct in @(
        (Join-Path $StagedDelivery $InstallerName),
        (Join-Path $StagedDelivery $PortableName)
    )) {
        Assert-RequiredFile $RequiredStagedProduct
    }

    foreach ($OuterFileName in $OuterFileSources.Keys) {
        Copy-Item `
            -LiteralPath $OuterFileSources[$OuterFileName] `
            -Destination (Join-Path $StagedOuterFiles $OuterFileName) `
            -Force
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
