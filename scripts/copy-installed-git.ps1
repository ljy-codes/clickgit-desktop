$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $ProjectRoot "runtime"
$Target = Join-Path $RuntimeRoot "git"
$Source = Split-Path (Split-Path (Get-Command git.exe).Source)

$RequiredFiles = @(
    "cmd\git.exe",
    "usr\bin\ssh.exe",
    "usr\bin\ssh-keygen.exe",
    "mingw64\bin\git-credential-manager.exe",
    "mingw64\bin\git-lfs.exe"
)
foreach ($RelativePath in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $Source $RelativePath))) {
        throw "Installed Git is missing required component: $RelativePath"
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
if (Test-Path -LiteralPath $Target) {
    $ResolvedRuntime = (Resolve-Path -LiteralPath $RuntimeRoot).Path
    $ResolvedTarget = (Resolve-Path -LiteralPath $Target).Path
    if (-not $ResolvedTarget.StartsWith($ResolvedRuntime, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace Git runtime outside the project runtime directory."
    }
    Remove-Item -LiteralPath $Target -Recurse -Force
}

Copy-Item -LiteralPath $Source -Destination $Target -Recurse
$Version = & (Join-Path $Target "cmd\git.exe") --version
Write-Host "Installed Git copied as ClickGit runtime: $Version"
