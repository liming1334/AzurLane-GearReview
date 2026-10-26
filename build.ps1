param(
    [switch]$OneFile
)
# 用法：
#   powershell -ExecutionPolicy Bypass -File build.ps1            # 免解压版（推荐）
#   powershell -ExecutionPolicy Bypass -File build.ps1 -OneFile   # 单文件版
$ErrorActionPreference = "Stop"
$root = "G:\azur lane"
$py = "C:\Users\黎明\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

$env:PYTHONPATH = Join-Path $root "vendor"
$env:TEMP = Join-Path $root ".tmp"
$env:TMP = Join-Path $root ".tmp"

$common = @(
    "--noconfirm", "--clean", "--windowed",
    "--name", "碧蓝装备排行",
    "--icon", "$root\assets\app.ico",
    "--add-data", "$root\data\equipment.json;data",
    "--add-data", "$root\assets\app.ico;assets",
    "--add-data", "$root\assets\icons;assets/icons",
    "--paths", $root,
    "$root\main.py"
)

if ($OneFile) {
    $mode = "--onefile"
    $dist = "$root\dist\单文件版"
    $work = "$root\build_onefile"
} else {
    $mode = "--onedir"
    $dist = "$root\dist"
    $work = "$root\build_onedir"
}

Set-Location $root
& $py -m PyInstaller $mode @common `
    --distpath $dist --workpath $work --specpath $work

if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }
Write-Host "输出目录: $dist"
