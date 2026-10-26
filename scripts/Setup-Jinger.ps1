param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Test-SupportedPython {
    param([string]$Executable, [string[]]$PrefixArguments = @())
    try {
        & $Executable @PrefixArguments -c "import sys,struct; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,12) and struct.calcsize('P')==8 else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Invoke-Python {
    param([string]$Executable, [string[]]$PythonArguments)
    & $Executable @PythonArguments
    if ($LASTEXITCODE -ne 0) { throw 'Python command failed. Review the output above and rerun setup after fixing the problem.' }
}

try {
    if ($CheckOnly) {
        if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
            throw 'No project environment exists yet. Run Setup Jinger.cmd first.'
        }
        if (-not (Test-SupportedPython $pythonPath)) { throw 'The project Python is broken or unsupported. Use 64-bit Python 3.11 or 3.12.' }
        Push-Location -LiteralPath $projectRoot
        try {
            & $pythonPath -m companion.app.doctor
            exit $LASTEXITCODE
        } finally { Pop-Location }
    }
    Write-Host 'Jinger setup: quit any running copy before updating its Python environment.'
    if (Test-Path -LiteralPath $pythonPath -PathType Leaf) {
        if (-not (Test-SupportedPython $pythonPath)) {
            throw 'The existing .venv is broken or unsupported. Install 64-bit Python 3.11 or 3.12, rename the old .venv folder, then rerun setup. Your data and .env stay separate.'
        }
        Write-Host 'Using the existing project environment.'
    } else {
        if (Test-Path -LiteralPath (Join-Path $projectRoot '.venv')) {
            throw 'An incomplete .venv folder exists. Rename it before rerunning setup; setup will not delete it.'
        }
        $basePython = $null
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pythonCommand -and $pythonCommand.Source -notlike '*\Microsoft\WindowsApps\*' -and
            (Test-SupportedPython $pythonCommand.Source)) { $basePython = $pythonCommand.Source }
        $pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $basePython -and $pyCommand) {
            # Listing installed runtimes avoids requesting an absent version from an install manager.
            try { $installedRuntimes = @(& $pyCommand.Source -0p 2>$null) }
            catch { $installedRuntimes = @() }
            foreach ($runtime in $installedRuntimes) {
                if ($runtime -match '(?<executable>[A-Za-z]:\\.*\\python\.exe)"?\s*$') {
                    $candidate = $Matches['executable']
                    if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and (Test-SupportedPython $candidate)) {
                        $basePython = $candidate
                        break
                    }
                }
            }
        }
        if (-not $basePython) { throw 'Install 64-bit Python 3.11 or 3.12 from python.org, then rerun Setup Jinger.cmd.' }
        Invoke-Python -Executable $basePython -PythonArguments @('-m', 'venv', (Join-Path $projectRoot '.venv'))
    }
    Invoke-Python $pythonPath @('-m', 'pip', 'install', '--upgrade', 'pip')
    # Install from the CPU wheel index first; no CUDA toolkit is required.
    Invoke-Python $pythonPath @('-m', 'pip', 'install', 'torch', '--index-url', 'https://download.pytorch.org/whl/cpu')
    Invoke-Python $pythonPath @('-m', 'pip', 'install', '-r', (Join-Path $projectRoot 'requirements.txt'))
    $envPath = Join-Path $projectRoot '.env'
    if (-not (Test-Path -LiteralPath $envPath)) {
        [IO.File]::Copy((Join-Path $projectRoot '.env.example'), $envPath, $false)
        Write-Host 'Created .env from the template. Add your OpenRouter key locally when ready.'
    } else { Write-Host 'Kept your existing .env unchanged.' }
    Push-Location -LiteralPath $projectRoot
    try { Invoke-Python $pythonPath @('-m', 'companion.app.doctor', '--engines') }
    finally { Pop-Location }
    Write-Host 'Setup complete. Double-click Start Jinger.cmd to launch.'
    exit 0
} catch {
    Write-Host ('Setup stopped: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
