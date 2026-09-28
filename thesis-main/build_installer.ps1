$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$distPath = Join-Path $projectRoot "dist"
$workPath = Join-Path $projectRoot "build"
$serverEntry = Join-Path $projectRoot "login.py"
$studentEntry = Join-Path $workspaceRoot "Student\login_student.py"

python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is required. Install it in the active Python environment with: python -m pip install pyinstaller"
}

python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name CompHub-Server --distpath $distPath --workpath (Join-Path $workPath "server") `
    --specpath $workPath --collect-all customtkinter `
    --add-data "$projectRoot\database\schema.sql;database" `
    --add-data "$projectRoot\network_config.json;." $serverEntry
if ($LASTEXITCODE -ne 0) { throw "Server packaging failed." }

python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name CompHub-Student --distpath $distPath --workpath (Join-Path $workPath "student") `
    --specpath $workPath --collect-all customtkinter --collect-all cv2 `
    --collect-all deepface --collect-all tensorflow `
    --add-data "$workspaceRoot\Student\network_config.json;." $studentEntry
if ($LASTEXITCODE -ne 0) { throw "Student packaging failed." }

$compilerPath = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $compilerPath) {
    $defaultCompiler = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
    if (Test-Path $defaultCompiler) { $compilerPath = $defaultCompiler }
}
if (-not $compilerPath) { throw "Inno Setup 6 is required to build the setup wizard." }

Push-Location $projectRoot
try {
    & $compilerPath (Join-Path $projectRoot "installer\CompHub.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
}
finally {
    Pop-Location
}