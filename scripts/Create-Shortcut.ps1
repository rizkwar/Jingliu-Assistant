param(
    [string]$Destination = [Environment]::GetFolderPath('Desktop'),
    [string]$Name = 'Jingliu',
    # The per-user Start menu is what Windows Search and the Start menu's app list index.
    [switch]$StartMenu
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ShortcutAppId.ps1')
if ($StartMenu) { $Destination = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs' }
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonWindowed = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$launchScript = Join-Path $projectRoot 'launch_jinger.pyw'
$shell = $null
$shortcut = $null
try {
    if (-not (Test-Path -LiteralPath $pythonWindowed -PathType Leaf)) { throw 'Run Setup Jinger.cmd before creating the shortcut.' }
    if (-not (Test-Path -LiteralPath $launchScript -PathType Leaf)) { throw 'launch_jinger.pyw is missing. Restore the project files.' }
    if (-not $Destination -or -not (Test-Path -LiteralPath $Destination -PathType Container)) { throw 'The shortcut destination folder does not exist.' }
    $shortcutPath = Join-Path $Destination ($Name + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $arguments = '"' + $launchScript + '"'
    if ((Test-Path -LiteralPath $shortcutPath) -and
        ($shortcut.TargetPath -ne $pythonWindowed -or $shortcut.Arguments -ne $arguments)) {
        throw 'A different shortcut with this name already exists. Rename it first; it was not overwritten.'
    }
    $shortcut.TargetPath = $pythonWindowed
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = 'Jingliu, your desktop companion'
    $shortcut.IconLocation = (Join-Path $projectRoot 'assets\jingliu.ico') + ',0'
    $shortcut.Save()
    # The same app ID as the running app: one taskbar icon, and a pinned shortcut that lights up.
    Set-ShortcutAppId $shortcutPath
    Write-Host ('Shortcut ready: ' + $shortcutPath)
    Write-Host 'Keep this project folder in place. If you move it, recreate the shortcut.'
    exit 0
} catch {
    Write-Host ('Shortcut not created: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    if ($shortcut) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shortcut) }
    if ($shell) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell) }
}
