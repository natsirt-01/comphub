$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$distPath = Join-Path $projectRoot "dist"
$workPath = Join-Path $projectRoot "build"
$serverEntry = Join-Path $projectRoot "login.py"
$studentEntry = Join-Path $workspaceRoot "Student\login_student.py"

if (-not (Test-Path $serverEntry)) { throw "Missing server entry point: $serverEntry" }
if (-not (Test-Path $studentEntry)) { throw "Missing student entry point: $studentEntry" }
if (-not (Test-Path (Join-Path $projectRoot "database\schema.sql"))) { throw "Missing database\schema.sql" }
if (-not (Test-Path (Join-Path $projectRoot "network_config.json"))) { throw "Missing server network_config.json" }
if (-not (Test-Path (Join-Path $workspaceRoot "Student\network_config.json"))) { throw "Missing Student\network_config.json" }

python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is required. Run: python -m pip install pyinstaller" }

python -m PyInstaller --noconfirm --clean --onedir --windowed `
  --name CompHub-Server --distpath $distPath --workpath (Join-Path $workPath "server") `
  --specpath $workPath --collect-all customtkinter `
  --add-data "$(Join-Path $projectRoot 'database\schema.sql');database" `
  --add-data "$(Join-Path $projectRoot 'network_config.json');." $serverEntry
if ($LASTEXITCODE -ne 0) { throw "Server packaging failed." }

python -m PyInstaller --noconfirm --clean --onedir --windowed `
  --name CompHub-Student --distpath $distPath --workpath (Join-Path $workPath "student") `
  --specpath $workPath --collect-all customtkinter --collect-all cv2 `
  --collect-all deepface --collect-all tensorflow `
  --add-data "$(Join-Path $workspaceRoot 'Student\network_config.json');." $studentEntry
if ($LASTEXITCODE -ne 0) { throw "Student packaging failed." }

$compilerPath = "C:\Users\Admin\AppData\Local\Programs\Inno Setup 6\ISCC.exe"

if (-not (Test-Path $compilerPath)) {
    throw "Inno Setup 6 compiler not found at: $compilerPath"
}

$iss = Join-Path $projectRoot "installer\CompHub.iss"

if (-not (Test-Path $iss)) {
    throw "Missing installer\CompHub.iss. Copy the provided replacement into this location."
}

Push-Location $projectRoot

try {
    Write-Host "Compiling CompHub Installer..." -ForegroundColor Cyan

    & $compilerPath $iss

    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Build finished. Look for installer-output\CompHub-Setup.exe" -ForegroundColor Green
