$ErrorActionPreference = "Stop"

$Version = "2.55.0.3"
$ExpectedGitVersion = "2.55.0.windows.3"
$ReleaseTag = "v2.55.0.windows.3"
$ArchiveName = "PortableGit-$Version-64-bit.7z.exe"
$ExpectedSha256 = "ab00566336b5472120f9a52d34f2e79c5406535792acb0548001ffd0bd090e5d"
$DownloadUrl = "https://github.com/git-for-windows/git/releases/download/$ReleaseTag/$ArchiveName"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $ProjectRoot "runtime"
$DownloadRoot = Join-Path $RuntimeRoot "downloads"
$ArchivePath = Join-Path $DownloadRoot $ArchiveName
$TemporaryArchive = "$ArchivePath.part"
$GitRoot = Join-Path $RuntimeRoot "git"
$GitExecutable = Join-Path $GitRoot "cmd\git.exe"

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

function Assert-NoReparseTree {
    param(
        [Parameter(Mandatory)]
        [string]$TrustedRoot,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $NormalizedRoot = Get-NormalizedPath $TrustedRoot
    $NormalizedPath = Get-NormalizedPath $Path
    $RequiredPrefix = $NormalizedRoot +
        [IO.Path]::DirectorySeparatorChar
    if (-not $NormalizedPath.StartsWith(
        $RequiredPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unsafe runtime path: $NormalizedPath"
    }
    $CurrentPath = $NormalizedRoot
    $RelativePath = $NormalizedPath.Substring(
        $NormalizedRoot.Length
    ).TrimStart(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    foreach ($PathPart in $RelativePath.Split(
        [char[]]@(
            [IO.Path]::DirectorySeparatorChar,
            [IO.Path]::AltDirectorySeparatorChar
        ),
        [StringSplitOptions]::RemoveEmptyEntries
    )) {
        $CurrentPath = Join-Path $CurrentPath $PathPart
        if (-not (Test-Path -LiteralPath $CurrentPath)) {
            return $NormalizedPath
        }
        $CurrentItem = Get-Item -LiteralPath $CurrentPath -Force
        if (
            ($CurrentItem.Attributes -band
                [IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "Reparse point is not allowed: $CurrentPath"
        }
    }
    if (Test-Path -LiteralPath $NormalizedPath -PathType Container) {
        $PendingPaths = New-Object "Collections.Generic.Queue[string]"
        $PendingPaths.Enqueue($NormalizedPath)
        while ($PendingPaths.Count -gt 0) {
            $CurrentDirectory = $PendingPaths.Dequeue()
            foreach ($ChildItem in Get-ChildItem `
                -LiteralPath $CurrentDirectory `
                -Force) {
                if (
                    ($ChildItem.Attributes -band
                        [IO.FileAttributes]::ReparsePoint) -ne 0
                ) {
                    throw (
                        "Reparse point is not allowed: " +
                        $ChildItem.FullName
                    )
                }
                if ($ChildItem.PSIsContainer) {
                    $PendingPaths.Enqueue($ChildItem.FullName)
                }
            }
        }
    }
    return $NormalizedPath
}

New-Item -ItemType Directory -Force -Path $DownloadRoot | Out-Null

if (Test-Path -LiteralPath $ArchivePath) {
    $ExistingHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ExistingHash -ne $ExpectedSha256) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
}

if (-not (Test-Path -LiteralPath $ArchivePath)) {
    Write-Host "Downloading official Git for Windows $ReleaseTag..."
    Remove-Item -LiteralPath $TemporaryArchive -Force -ErrorAction SilentlyContinue
    & curl.exe `
        --fail `
        --location `
        --retry 4 `
        --retry-delay 3 `
        --output $TemporaryArchive `
        $DownloadUrl
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $TemporaryArchive -Force -ErrorAction SilentlyContinue
        throw "PortableGit download failed."
    }
    Move-Item -LiteralPath $TemporaryArchive -Destination $ArchivePath
}

$ActualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    throw "PortableGit checksum mismatch. Expected $ExpectedSha256, got $ActualSha256."
}

if (Test-Path -LiteralPath $GitRoot) {
    Assert-NoReparseTree `
        -TrustedRoot $ProjectRoot `
        -Path $GitRoot | Out-Null
    Remove-Item -LiteralPath $GitRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $GitRoot | Out-Null
& $ArchivePath -y "-o$GitRoot" | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $GitExecutable)) {
    throw "PortableGit extraction failed."
}

$VersionOutput = & $GitExecutable --version
if ($VersionOutput -ne "git version $ExpectedGitVersion") {
    throw (
        "PortableGit runtime version mismatch. Expected " +
        "'git version $ExpectedGitVersion', got '$VersionOutput'."
    )
}
Write-Host "PortableGit ready: $VersionOutput"
