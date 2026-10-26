param([switch]$CheckOnly)

# Optional natural voice engine. It lives in its own environment because Chatterbox pins
# PyTorch and Transformers versions that differ from the assistant's. Nothing here changes
# the assistant's .venv, .env, data or the default Pocket TTS voice.
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$lab = Join-Path $projectRoot '.cache\voice-lab'
$python = Join-Path $lab 'venv\Scripts\python.exe'
try {
    if ($CheckOnly) {
        if (-not (Test-Path -LiteralPath $python)) { Write-Host 'Chatterbox is not installed. Run More\Setup Chatterbox.cmd.'; exit 1 }
        & $python -c "import torch, chatterbox, sounddevice; print('Chatterbox ready on', 'GPU (' + torch.cuda.get_device_name(0) + ')' if torch.cuda.is_available() else 'CPU only (slow)')"
        exit $LASTEXITCODE
    }
    if (-not (Test-Path -LiteralPath $python)) {
        Write-Host 'Creating the Chatterbox environment in .cache\voice-lab ...'
        New-Item -ItemType Directory -Force -Path $lab | Out-Null
        if (Get-Command py -ErrorAction SilentlyContinue) { & py -3.11 -m venv (Join-Path $lab 'venv') }
        else { & python -m venv (Join-Path $lab 'venv') }
        if ($LASTEXITCODE) { throw 'Python 3.11 could not create the environment.' }
    }
    & $python -m pip install --upgrade pip
    & $python -m pip install chatterbox-tts sounddevice
    if ($LASTEXITCODE) { throw 'Installing Chatterbox failed. Check your internet connection and try again.' }
    $gpu = $false
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) { & nvidia-smi -L *> $null; $gpu = ($LASTEXITCODE -eq 0) }
    if ($gpu) {
        Write-Host 'NVIDIA GPU found: installing the CUDA build of PyTorch for real-time speech ...'
        & $python -m pip install --force-reinstall torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
        if ($LASTEXITCODE) { throw 'Installing GPU support failed. Chatterbox still works on the CPU, slowly.' }
    } else {
        Write-Host 'No working NVIDIA GPU detected, so Chatterbox will run on the CPU (much slower than real time).'
        Write-Host 'If your laptop has one, switch it on (GPU mode in the laptop app or BIOS), then run this setup again.'
    }
    & $python -c "import torch, chatterbox, sounddevice; print('Chatterbox ready on', 'GPU (' + torch.cuda.get_device_name(0) + ')' if torch.cuda.is_available() else 'CPU only (slow)')"
    Write-Host 'The model (about 3 GB) downloads the first time Jingliu speaks with Chatterbox.'
    exit 0
} catch {
    Write-Host ('Chatterbox setup did not finish: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
