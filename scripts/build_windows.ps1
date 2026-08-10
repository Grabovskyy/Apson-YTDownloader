param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExecutable,
    [Parameter(Mandatory = $true)]
    [string]$BuildRoot,
    [Parameter(Mandatory = $true)]
    [string]$ArtifactsRoot,
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
$ArtifactsRoot = [IO.Path]::GetFullPath($ArtifactsRoot)
$PythonExecutable = [IO.Path]::GetFullPath($PythonExecutable)

foreach ($target in @($BuildRoot, $ArtifactsRoot)) {
    if ($target -eq [IO.Path]::GetPathRoot($target) -or $target.StartsWith($ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Katalog builda i artefaktów musi znajdować się poza repozytorium: $target"
    }
}
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw "Nie znaleziono interpretera: $PythonExecutable"
}

$Version = (& $PythonExecutable -c "import sys; sys.path.insert(0, sys.argv[1]); from app import __version__; print(__version__)" $ProjectRoot).Trim()
if ($LASTEXITCODE -ne 0 -or $Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Nie udało się odczytać poprawnej wersji aplikacji."
}

$env:PIP_CACHE_DIR = Join-Path $BuildRoot "pip-cache"
$env:TEMP = Join-Path $BuildRoot "temp"
$env:TMP = $env:TEMP
$env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildRoot "pyinstaller-cache"
New-Item -ItemType Directory -Force -Path $BuildRoot, $ArtifactsRoot, $env:PIP_CACHE_DIR, $env:TEMP, $env:PYINSTALLER_CONFIG_DIR | Out-Null

& $PythonExecutable (Join-Path $ProjectRoot "scripts\create_brand_assets.py")
if ($LASTEXITCODE -ne 0) { throw "Generowanie ikony nie powiodło się." }

& $PythonExecutable -m unittest discover -s (Join-Path $ProjectRoot "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Testy nie przeszły." }

$WorkPath = Join-Path $BuildRoot "pyinstaller-work"
$DistPath = Join-Path $BuildRoot "dist"
$SpecPath = Join-Path $ProjectRoot "packaging\windows\ApsonYTDownloader.spec"
& $PythonExecutable -m PyInstaller --noconfirm --clean --workpath $WorkPath --distpath $DistPath $SpecPath
if ($LASTEXITCODE -ne 0) { throw "PyInstaller nie zbudował aplikacji." }

$Onedir = Join-Path $DistPath "ApsonYTDownloader"
if (-not (Test-Path -LiteralPath (Join-Path $Onedir "ApsonYTDownloader.exe") -PathType Leaf)) {
    throw "Brak ApsonYTDownloader.exe po buildzie."
}

$SelfTestData = Join-Path $BuildRoot "self-test-data"
$SelfTestReport = Join-Path $BuildRoot "self-test-report.json"
$PreviousDataDir = $env:YTDOWNLOADER_DATA_DIR
$env:YTDOWNLOADER_DATA_DIR = $SelfTestData
try {
    & (Join-Path $Onedir "ApsonYTDownloader.exe") --self-test $SelfTestReport
    if ($LASTEXITCODE -ne 0) { throw "Self-test zamrozonej aplikacji nie przeszedl." }
    if (-not (Test-Path -LiteralPath $SelfTestReport -PathType Leaf)) {
        throw "Zamrozona aplikacja nie utworzyla raportu self-test."
    }
    $SelfTestResult = Get-Content -LiteralPath $SelfTestReport -Raw | ConvertFrom-Json
    if (-not $SelfTestResult.ok) { throw "Raport self-test zamrozonej aplikacji zawiera bledy." }
}
finally {
    if ($null -eq $PreviousDataDir) {
        Remove-Item Env:YTDOWNLOADER_DATA_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:YTDOWNLOADER_DATA_DIR = $PreviousDataDir
    }
}

$PortableRoot = Join-Path $BuildRoot "portable\ApsonYTDownloader"
if (Test-Path -LiteralPath $PortableRoot) { Remove-Item -LiteralPath $PortableRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null
Copy-Item -Path (Join-Path $Onedir "*") -Destination $PortableRoot -Recurse -Force
New-Item -ItemType File -Force -Path (Join-Path $PortableRoot ".portable") | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "packaging\PORTABLE_README.txt") -Destination (Join-Path $PortableRoot "README_PORTABLE.txt") -Force

$PortableZip = Join-Path $ArtifactsRoot "Apson-YTDownloader-Portable-$Version.zip"
if (Test-Path -LiteralPath $PortableZip) { Remove-Item -LiteralPath $PortableZip -Force }
Compress-Archive -Path $PortableRoot -DestinationPath $PortableZip -CompressionLevel Optimal

if ($InnoCompiler) {
    $InnoCompiler = [IO.Path]::GetFullPath($InnoCompiler)
    if (-not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)) {
        throw "Nie znaleziono kompilatora Inno Setup: $InnoCompiler"
    }
    $InstallerScript = Join-Path $ProjectRoot "packaging\windows\installer.iss"
    & $InnoCompiler "/DBuildSource=$Onedir" "/DAppVersion=$Version" "/O$ArtifactsRoot" $InstallerScript
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup nie zbudował installera." }
}

& $PythonExecutable (Join-Path $ProjectRoot "scripts\create_artifact_manifest.py") $ArtifactsRoot $Version
if ($LASTEXITCODE -ne 0) { throw "Nie udało się utworzyć manifestu artefaktów." }

Write-Output "ONEDIR=$Onedir"
Write-Output "PORTABLE=$PortableZip"
Write-Output "ARTIFACTS=$ArtifactsRoot"
