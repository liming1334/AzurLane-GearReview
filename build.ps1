param(
    [string]$Python = "python"
)
# 用法：
#   powershell -ExecutionPolicy Bypass -File build.ps1
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Python "C:\path\to\python.exe"
# 输出（本地，不入库）：
#   打包\碧蓝装备排行_单文件版.exe
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$vendor = Join-Path $root "vendor"
if (Test-Path -LiteralPath $vendor) {
    $env:PYTHONPATH = $vendor
}

$common = @(
    "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "碧蓝装备排行_单文件版",
    "--icon", "$root\assets\app.ico",
    # 两个数据文件都要带：缺 plane_weapons.json 时舰载机拿不到挂载数值，整类无分
    "--add-data", "$root\data\equipment.json;data",
    "--add-data", "$root\data\plane_weapons.json;data",
    "--add-data", "$root\assets\app.ico;assets",
    "--add-data", "$root\assets\icons;assets/icons",
    # numpy/pandas 会被 Pillow 的依赖分析带进来，排除后体积更小
    "--exclude-module", "numpy",
    "--exclude-module", "pandas",
    "--exclude-module", "matplotlib",
    "--exclude-module", "scipy",
    "--paths", $root,
    "$root\main.py"
)

Set-Location $root
& $Python -m PyInstaller @common `
    --distpath "$root\打包" --workpath "$root\build" --specpath "$root\build"

if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }
Write-Host "输出: $root\打包\碧蓝装备排行_单文件版.exe"
