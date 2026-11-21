$ErrorActionPreference = 'Stop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $taskDocker = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
    if (-not (Test-Path -LiteralPath $taskDocker)) { $taskDocker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' }
    if (-not (Test-Path -LiteralPath $taskDocker)) { throw 'Docker Desktop 설치를 확인하세요.' }
    Set-Alias -Name docker -Value $taskDocker -Scope Script
}
# Stops only this practice container. Model volumes and other services are kept.
& docker stop bom-qwen08-demo
if ($LASTEXITCODE -ne 0) { throw '실습 컨테이너 이름과 현재 상태를 확인하세요.' }
