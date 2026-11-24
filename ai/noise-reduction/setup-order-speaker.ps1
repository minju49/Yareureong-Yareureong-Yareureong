$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$python = '.\.venv\Scripts\python.exe'
& $python -m pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pip install -r requirements-order-speaker.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -c 'import torch, sherpa_onnx; assert torch.cuda.is_available(), "NVIDIA CUDA unavailable"'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python model_files.py --ensemble
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python order_speaker_models.py
exit $LASTEXITCODE
