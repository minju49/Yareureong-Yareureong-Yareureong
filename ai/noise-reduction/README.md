# 입력별 잡음 제거 조합 비교

같은 음성을 원본, 단일 모델, 두 모델 조합으로 처리해 재생하고 동일한 STT로 비교하는 로컬 실험 도구다. 자동 선택과 평가 결과는 [실험 기록](results/README.md)에 정리했다.

| 모드 | 처리 |
|---|---|
| OFF | 공통 전처리만 수행한다. |
| ON | 원본 75%와 ZipEnhancer 출력 25%를 섞는다. |
| MossFormerGAN | 원본 75%와 MossFormerGAN 출력 25%를 섞는다. |
| 병렬 조합 | 원본 75%, 각 모델 출력 12.5%씩 섞는다. |
| 두 직렬 조합 | 첫 번째 추정 음성을 원본에 일부 섞은 뒤 두 번째 모델에 넣고, 두 번째 결과도 일부만 반영한다. 적용 순서를 바꿔 비교할 수 있다. |
| AUTO | 16kHz WAV를 512샘플 단위로 나눠 프레임 평균 제곱값의 20·80 백분위수 비율을 구한다. 고정한 두 임계값으로 ZipEnhancer 단독과 두 직렬 조합 중 하나를 선택한다. 디지털 무음은 OFF로 통과시키며, 2~8초 범위를 벗어나면 ON을 적용한다. |

두 모델은 사전학습 가중치를 사용한다. 조합 비율과 적용 순서, 길이 보존을 위한 겹침 합성, 입력 특징 기반의 선택 로직을 구현했다. 팀의 주문 웹과는 독립적으로 실행하며, 화면에 WAV 파일을 올려 비교한다.

## Windows 설치와 실행

검증한 환경은 Python 3.11, NVIDIA RTX 5060, PyTorch와 TorchAudio 2.7.1+cu128이다. 조합은 CUDA GPU가 필요하다. 저장소 루트의 PowerShell에서 실행한다.

```powershell
cd ai/noise-reduction
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements-ensemble.txt
.\.venv\Scripts\python.exe model_files.py --ensemble
.\실행.cmd
```

브라우저에서 http://127.0.0.1:8058/ 을 열고 WAV를 선택한다. 모드를 바꾸면 같은 입력을 다시 처리하며, 실제 선택된 경로와 추론 시간, 원본·처리 WAV가 표시된다.

체크포인트는 최초 한 번 `models/zipenhancer/`와 `models/mossformer-gan/`에 내려받아 SHA-256을 검증한다. ZipEnhancer 기존 파일은 `ZIPENHANCER_MODEL_DIR`로 지정할 수 있다. 체크포인트와 가상환경은 Git에서 제외한다. 최초 MossFormerGAN 요청 시간에는 모델 로딩이 포함된다.

SenseVoiceSmall 인식 결과까지 비교하려면 별도로 설치한 `sherpa-onnx` 환경의 Python 실행 파일과 `model.int8.onnx`, `tokens.txt`가 들어 있는 모델 폴더를 지정한다. 두 환경 변수는 서버를 실행하기 전에 설정한다.

```powershell
$env:ZIP_STT_PYTHON = 'D:\path\to\stt-venv\Scripts\python.exe'
$env:ZIP_STT_MODEL_DIR = 'D:\path\to\sensevoice-small'
.\실행.cmd
```

## API와 검증

`POST /denoise`의 기존 `enabled=false|true`는 OFF/ON에 대응한다. `mode`로 `off`, `zipenhancer`, `mossgan`, `parallel`, `moss_to_zip`, `zip_to_moss`, `auto`를 직접 지정할 수 있다. 결과는 16kHz 모노 float32 WAV이며, 응답 헤더의 `X-Mode`, `X-Denoise-Applied`, `X-Strength`, `X-Inference-Seconds`로 처리 정보를 확인할 수 있다. 최대 60초, 25MiB의 WAV를 받는다. `/compare`는 같은 입력의 두 WAV와 선택 경로를 JSON으로 반환한다. API 문서는 http://127.0.0.1:8058/docs 에서 확인할 수 있다.

```powershell
curl.exe --fail -sS -F "file=@input.wav" -F "mode=auto" http://127.0.0.1:8058/denoise -o auto.wav
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe verify_api.py
.\.venv\Scripts\python.exe verify_ensemble.py
```

검증 스크립트는 합성 파형을 사용하므로 AI Hub 음성 파일이 필요 없다. STT 환경 변수를 지정한 경우 실제 STT 호출도 검증한다.
