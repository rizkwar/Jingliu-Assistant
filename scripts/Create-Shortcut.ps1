param([string]$Destination = [Environment]::GetFolderPath('Desktop'))

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonWindowed = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$launchScript = Join-Path $projectRoot 'launch_mira.pyw'
$shell = $null
$shortcut = $null
try {
    if (-not (Test-Path -LiteralPath $pythonWindowed -PathType Leaf)) { throw 'Run Setup Mira.cmd before creating the shortcut.' }
    if (-not (Test-Path -LiteralPath $launchScript -PathType Leaf)) { throw 'launch_mira.pyw is missing. Restore the project files.' }
    if (-not $Destination -or -not (Test-Path -LiteralPath $Destination -PathType Container)) { throw 'The shortcut destination folder does not exist.' }
    $shortcutPath = Join-Path $Destination 'Mira Desktop Companion.lnk'
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
    $shortcut.Description = 'Open the desktop companion from this project folder'
    $shortcut.IconLocation = (Join-Path $projectRoot 'assets\mira.ico') + ',0'
    $shortcut.Save()
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
