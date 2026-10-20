<#
.SYNOPSIS
    Publishes the self-contained ScriptHost .NET assembly for each target
    runtime identifier and copies the output into the Python package so it
    ships inside the wheel (no separate .NET install required at runtime).

.DESCRIPTION
    - linux-x64 : required for deployment inside Microsoft Fabric (Spark pools
                  run on Linux x64 nodes).
    - win-x64   : convenience build for local development/testing on Windows.

    Run from the repository root:
        .\build.ps1
#>
param(
    [string[]]$RuntimeIdentifiers = @("linux-x64", "win-x64"),
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$projectPath = Join-Path $root "ScriptHost\ScriptHost.csproj"
$pkgRuntimeRoot = Join-Path $root "python\fabric_csharp\runtime"

foreach ($rid in $RuntimeIdentifiers) {
    Write-Host "==> Publishing ScriptHost for $rid ..." -ForegroundColor Cyan

    $fxDir = Join-Path $root "ScriptHost\bin\$Configuration\net10.0\$rid\fxpublish"
    $scDir = Join-Path $root "ScriptHost\bin\$Configuration\net10.0\$rid\publish"

    # Framework-dependent publish: gives us the app's own files (ScriptHost.dll,
    # its Roslyn dependencies, deps.json) plus a runtimeconfig.json that declares
    # a normal "frameworks" requirement (NOT the self-contained shape, which
    # clr_loader/hostfxr refuses to use for in-process component hosting).
    dotnet publish $projectPath -c $Configuration -r $rid --self-contained false -o $fxDir
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish (framework-dependent) failed for $rid" }

    # Self-contained publish: same app, but with the actual CoreCLR runtime
    # binaries for $rid bundled alongside. We only want those runtime binaries
    # (not the app files, which we already have from the fx publish above).
    dotnet publish $projectPath -c $Configuration -r $rid --self-contained true -o $scDir
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish (self-contained) failed for $rid" }

    $appFiles = @((Get-ChildItem $fxDir -File) | ForEach-Object { $_.Name })
    $runtimeFiles = @((Get-ChildItem $scDir -File) | Where-Object { -not ($appFiles -contains $_.Name) })

    $frameworkVersion = (Get-Content (Join-Path $fxDir "ScriptHost.runtimeconfig.json") -Raw | ConvertFrom-Json).runtimeOptions.framework.version

    $targetDir = Join-Path $pkgRuntimeRoot $rid
    $appTarget = Join-Path $targetDir "app"
    $sharedTarget = Join-Path $targetDir "dotnetroot\shared\Microsoft.NETCore.App\$frameworkVersion"

    if (Test-Path $targetDir) { Remove-Item $targetDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $appTarget | Out-Null
    New-Item -ItemType Directory -Force -Path $sharedTarget | Out-Null

    Copy-Item (Join-Path $fxDir "*") $appTarget -Recurse -Force
    Copy-Item $runtimeFiles.FullName $sharedTarget -Force

    # hostfxr is the .NET "host resolver" component and must live in its own
    # host/fxr/<version>/ folder (standard dotnet install layout) - NOT inside
    # shared/Microsoft.NETCore.App, even though self-contained publish bundles
    # it flat alongside the framework files.
    $hostfxrName = if ($rid -like "win-*") { "hostfxr.dll" } else { "libhostfxr.so" }
    $hostfxrSource = Join-Path $sharedTarget $hostfxrName
    if (Test-Path $hostfxrSource) {
        $hostfxrTarget = Join-Path $targetDir "dotnetroot\host\fxr\$frameworkVersion"
        New-Item -ItemType Directory -Force -Path $hostfxrTarget | Out-Null
        Move-Item $hostfxrSource (Join-Path $hostfxrTarget $hostfxrName) -Force
    }

    # hostfxr/hostpolicy also require a <Framework>.deps.json describing the
    # runtime's native assets (coreclr.dll etc.) to resolve the CoreCLR path.
    # The self-contained publish's own deps.json already contains a full
    # "runtimepack.Microsoft.NETCore.App.Runtime.<rid>" entry listing every
    # native/runtime file - reuse it verbatim (extra entries are harmless).
    Copy-Item (Join-Path $scDir "ScriptHost.deps.json") (Join-Path $sharedTarget "Microsoft.NETCore.App.deps.json") -Force

    # hostfxr only recognizes a shared/Microsoft.NETCore.App/<version> folder as a
    # valid installed framework if it contains a ".version" marker file
    # (commit-hash line + version line), matching a real `dotnet` installation.
    "0000000000000000000000000000000000000000`n$frameworkVersion" |
        Set-Content -NoNewline -Path (Join-Path $sharedTarget ".version") -Encoding ascii

    $sizeMb = [math]::Round((Get-ChildItem $targetDir -Recurse | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host "    -> $targetDir  ($sizeMb MB, framework $frameworkVersion)" -ForegroundColor Green
}

Write-Host "Done. Runtime assets staged under python\fabric_csharp\runtime\<rid>\" -ForegroundColor Cyan
