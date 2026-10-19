param(
    [Parameter(Mandatory=$true)][string] $StageRoot
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source = Join-Path $repo 'builder\BravePortable.cs'
$icon = Join-Path $StageRoot 'App\AppInfo\appicon.ico'
$destination = Join-Path $StageRoot 'BravePortable.exe'
if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Launcher source missing: $source" }
if (!(Test-Path -LiteralPath $icon -PathType Leaf)) { throw "Original Brave icon missing: $icon" }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) { throw "Windows .NET Framework C# compiler missing: $compiler" }
& $compiler /nologo /target:winexe "/out:$destination" "/win32icon:$icon" /reference:System.Windows.Forms.dll "$source"
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $destination)) { throw 'Brave Portable launcher compilation failed.' }
Write-Host "Created official-icon launcher: $destination"
