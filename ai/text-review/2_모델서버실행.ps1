$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskContainer = 'bom-qwen08-demo'
# Verified nightly image, pinned so future runs use the same build.
$taskImage = 'vllm/vllm-openai@sha256:16721463e5ae0c81623c65c50f5b8d4e37710d9bc4f6f4f7512ec1939096272f'
$taskModel = 'Qwen/Qwen3.5-0.8B'
$taskRevision = '2fc06364715b967f1860aea9cf38778875588b17'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $taskDockerCandidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
        'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
    )
    $taskDockerPath = $taskDockerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $taskDockerPath) { throw 'Docker Desktop을 설치하고 실행한 뒤 다시 실행하세요.' }
    Set-Alias -Name docker -Value $taskDockerPath -Scope Script
}
$taskOsType = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop이 준비되지 않았습니다. Engine running을 확인하세요.' }
if ($taskOsType -ne 'linux') { throw 'Docker Desktop을 Linux containers로 전환한 뒤 다시 실행하세요.' }
$taskExisting = & docker ps -a --filter "name=^/$taskContainer$" --format '{{.Names}}'
if ($taskExisting) {
    $taskInspect = (& docker inspect $taskContainer --format '{{json .}}') | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $taskInspect.Config.Labels.project -ne 'bom-qwen08-practice') {
        throw '같은 이름의 다른 컨테이너가 있습니다. 기존 파일을 유지했으니 실행 기록을 확인하세요.'
    }
    if ($taskInspect.State.Status -eq 'exited' -or $taskInspect.State.Status -eq 'created') {
        & docker start $taskContainer
        if ($LASTEXITCODE -ne 0) { throw '기존 실습 서버를 다시 시작하지 못했습니다.' }
        Write-Host '받아둔 모델과 실행 환경으로 서버를 다시 시작했어요.'
    } elseif ($taskInspect.State.Status -eq 'running') {
        Write-Host '이 실습 서버가 이미 실행 중이에요.'
    } else {
        throw ('실습 서버 상태를 확인하세요: ' + $taskInspect.State.Status)
    }
    Write-Host '모델 준비 후 3_주문호출시험.cmd를 누르세요.'
    Write-Host '진행 보기: docker logs -f bom-qwen08-demo'
    exit 0
}
Write-Host '공식 vLLM 이미지를 준비합니다. 첫 실행에는 큰 파일 다운로드가 있습니다.'
& docker pull $taskImage
if ($LASTEXITCODE -ne 0) { throw '이미지 다운로드가 실패했습니다.' }
$taskImageId = & docker image inspect $taskImage --format '{{.Id}}'
if ($LASTEXITCODE -ne 0 -or -not $taskImageId) { throw '다운로드한 이미지 정보를 확인하지 못했습니다.' }
& docker run --rm --gpus all --entrypoint python3 $taskImageId -c "import torch; print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_properties(0).total_memory)"
if ($LASTEXITCODE -ne 0) { throw '컨테이너의 GPU 사용 확인에 실패했습니다. 모델을 실행하지 않았습니다.' }
$taskArgs = @('run','--detach','--name',$taskContainer,'--gpus','all',
    '--publish','127.0.0.1:18080:8000','--shm-size','1g',
    '--volume','bom-qwen08-hf:/root/.cache/huggingface',
    '--volume','bom-qwen08-compile:/root/.cache/vllm',
    '--label','project=bom-qwen08-practice',$taskImageId,
    '--model',$taskModel,'--served-model-name',$taskModel,
    '--revision',$taskRevision,
    '--max-model-len','4096','--max-num-seqs','1',
    '--gpu-memory-utilization','0.70','--enforce-eager','--language-model-only')
& docker @taskArgs
if ($LASTEXITCODE -ne 0) { throw '모델 서버 실행에 실패했습니다.' }
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'records') -Force | Out-Null
& docker image inspect $taskImage --format '{{json .RepoDigests}}' | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'records\image-digest.json') -Encoding UTF8
$taskImageId | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'records\image-id.txt') -Encoding UTF8
$taskArgs | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'records\launch-args.json') -Encoding UTF8
Write-Host '시작 요청을 보냈습니다. 아직 모델 준비 완료를 의미하지는 않습니다.'
Write-Host '진행 보기: docker logs -f bom-qwen08-demo'
Write-Host '준비 후 3_주문호출시험.cmd를 누르세요.'
Write-Host '주소: http://127.0.0.1:18080/v1'
