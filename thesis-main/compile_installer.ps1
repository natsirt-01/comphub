$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$compilerPath = "C:\Users\Admin\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
$iss = Join-Path $projectRoot "installer\CompHub.iss"

if (-not (Test-Path $compilerPath)) {
    throw "Inno Setup compiler not found."
}

if (-not (Test-Path $iss)) {
    throw "CompHub.iss not found."
}

Write-Host "Compiling CompHub Installer..." -ForegroundColor Cyan

& $compilerPath $iss

if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed."
}

Write-Host "SUCCESS! Check installer-output\CompHub-Setup.exe" -ForegroundColor Green