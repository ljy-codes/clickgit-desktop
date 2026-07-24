$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$GitExecutable = Join-Path $ProjectRoot "runtime\git\cmd\git.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & (Join-Path $PSScriptRoot "bootstrap.ps1")
}
if (-not (Test-Path -LiteralPath $GitExecutable)) {
    & (Join-Path $PSScriptRoot "download-portable-git.ps1")
}

Push-Location $ProjectRoot
try {
    $env:PYTHONPATH = "src"
    $env:QT_QPA_PLATFORM = "offscreen"
    & $VenvPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed."
    }
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    & $VenvPython -m PyInstaller --noconfirm --clean packaging\clickgit.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Build completed: $(Join-Path $ProjectRoot 'dist\ClickGit\ClickGit.exe')"
