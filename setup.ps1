# Default action produces a reviewable plan; it never installs dependencies.
param(
    [Parameter(Mandatory = $true)][string]$Project,
    [ValidateSet("antigravity", "vscode", "both")][string]$IDE = "antigravity",
    [ValidateSet("existing", "install", "skip")][string]$Graphify = "existing",
    [switch]$Smoke,
    [switch]$PNGGrid,
    [string]$Godot
)
$ErrorActionPreference = "Stop"
$BootstrapPath = Join-Path $PSScriptRoot "bootstrap.py"
$SetupArgs = @($BootstrapPath, "plan", "--project", $Project, "--ide", $IDE, "--graphify", $Graphify)
if ($Smoke) { $SetupArgs += "--smoke" }
if ($PNGGrid) { $SetupArgs += "--png-grid" }
if ($Godot) { $SetupArgs += @("--godot", $Godot) }
& python @SetupArgs
exit $LASTEXITCODE
