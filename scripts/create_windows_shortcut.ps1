param(
    [string]$RepoWindowsPath = "",
    [string]$ShortcutName = "AVAC GUI",
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"

if (-not $RepoWindowsPath) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepoWindowsPath = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..")).Path
} else {
    $RepoWindowsPath = (Resolve-Path -LiteralPath $RepoWindowsPath).Path
}

$wslExe = Join-Path $env:WINDIR "System32\wsl.exe"
if (-not (Test-Path -LiteralPath $wslExe)) {
    throw "wsl.exe was not found. Install WSL first."
}

$repoWslPath = (& $wslExe wslpath -a "$RepoWindowsPath" 2>$null | Out-String).Trim()
if (-not $repoWslPath) {
    throw "Could not convert repository path to WSL path: $RepoWindowsPath"
}

$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath ("{0}.lnk" -f $ShortcutName)
if ((Test-Path -LiteralPath $shortcutPath) -and -not $Overwrite) {
    throw "Shortcut already exists: $shortcutPath (use -Overwrite to replace)"
}

$bashCommand = "cd '$repoWslPath' && source env/bin/activate && python avac_gui.py"
$arguments = "-e bash -lc `"$bashCommand`""

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wslExe
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $RepoWindowsPath
$shortcut.Description = "Launch AVAC GUI inside WSL"
$shortcut.IconLocation = "$wslExe,0"
$shortcut.Save()

Write-Host "Created shortcut: $shortcutPath"
Write-Host "Target repository: $RepoWindowsPath"
