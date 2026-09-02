$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PackageRoot = Join-Path $ProjectRoot "artifacts\publish\windows-x64\ClickGit"
$Executable = Join-Path $PackageRoot "ClickGit.exe"
$BundledGit = Join-Path $PackageRoot "runtime\git\cmd\git.exe"
$Report = Join-Path $ProjectRoot "artifacts\build\windows\package-smoke.json"

if (-not (Test-Path -LiteralPath $Executable)) {
    throw "ClickGit.exe was not found. Run scripts\build.ps1 first."
}
if (-not (Test-Path -LiteralPath $BundledGit)) {
    throw "Bundled git.exe was not found in the package."
}

New-Item -ItemType Directory -Force -Path (Split-Path $Report) | Out-Null
$Process = Start-Process -FilePath $Executable `
    -ArgumentList @("--smoke-test", $Report) `
    -WindowStyle Hidden `
    -Wait `
    -PassThru
if ($Process.ExitCode -ne 0) {
    throw "Packaged ClickGit smoke test failed with exit code $($Process.ExitCode)."
}

$Diagnostic = Get-Content -LiteralPath $Report -Encoding UTF8 -Raw |
    ConvertFrom-Json
$ExpectedGit = (Resolve-Path -LiteralPath $BundledGit).Path
if ($Diagnostic.git_returncode -ne 0) {
    throw "Bundled Git diagnostic failed."
}
if (-not $Diagnostic.gui_started) {
    throw "Packaged GUI smoke test did not complete."
}
if ($Diagnostic.git_executable -ne $ExpectedGit) {
    throw "Package used an unexpected Git executable: $($Diagnostic.git_executable)"
}

Write-Host "Package verified with $($Diagnostic.git_version)"
