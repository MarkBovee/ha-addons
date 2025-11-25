param(
  [string]$addon,
  [string]$env,
  [switch]$list,
  [switch]$dryRun
)

$script = Join-Path $PSScriptRoot "run_addon.py"

$argsList = @()
if ($addon) { $argsList += "--addon"; $argsList += $addon }
if ($env) { $argsList += "--env"; $argsList += $env }
if ($list) { $argsList += "--list" }
if ($dryRun) { $argsList += "--dry-run" }

python $script @argsList
