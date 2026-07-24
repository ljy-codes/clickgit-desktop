$ErrorActionPreference = "Stop"

$Version = "2.55.0.3"
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
    $ResolvedRuntime = (Resolve-Path -LiteralPath $RuntimeRoot).Path
    $ResolvedGit = (Resolve-Path -LiteralPath $GitRoot).Path
    if (-not $ResolvedGit.StartsWith($ResolvedRuntime, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace Git runtime outside the project runtime directory."
    }
    Remove-Item -LiteralPath $GitRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $GitRoot | Out-Null
& $ArchivePath -y "-o$GitRoot" | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $GitExecutable)) {
    throw "PortableGit extraction failed."
}

$VersionOutput = & $GitExecutable --version
Write-Host "PortableGit ready: $VersionOutput"
