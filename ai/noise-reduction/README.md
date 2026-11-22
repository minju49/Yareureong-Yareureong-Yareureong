# ZipEnhancer 잡음 제거 비교

AI 담당의 잡음 제거 구현과 실험 결과다. 음성 입력과 STT 사이에서 WAV 파일을 받아 16kHz 모노 WAV로 반환한다. 기본은 OFF이며, ON은 원본 75%와 ZipEnhancer 출력 25%를 혼합한다. [실험 결과](results/README.md)를 함께 참고한다.

- `server.py`는 비교 API를 제공한다.
- `zip_denoiser.py`는 모델 추론, 출력의 길이 보존과 겹침 합성을 처리한다.
- `model_files.py`는 [공식 모델 체크포인트](https://modelscope.cn/models/iic/speech_zipenhancer_ans_multiloss_16k_base)를 내려받고 검증에 사용한 파일의 SHA-256과 대조한다.
- 이 폴더는 잡음 제거 모듈이다. 팀의 Spring Boot·STT·주문 API와 실제 마이크 통합은 별도 단계다. 기존 ZipEnhancer 키오스크 연동 결과는 실험 기록에 포함한다.

## 설치와 실행

검증 환경은 Windows, Python 3.11, NVIDIA RTX 5060, PyTorch `2.7.1+cu128`이다. 명령은 저장소 루트의 PowerShell에서 실행한다.

```powershell
cd ai/noise-reduction
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe model_files.py
.\실행.cmd
```

체크포인트는 처음 한 번 `models/zipenhancer/`에 다운로드된다. 이미 같은 체크포인트가 있으면 `ZIPENHANCER_MODEL_DIR` 환경 변수로 위치를 지정할 수 있다. 모델과 가상환경은 Git에서 제외한다.

## 같은 입력으로 비교하기

다른 PowerShell에서 `input.wav`를 준비한 뒤 아래처럼 실행한다. OpenAPI 화면은 `http://127.0.0.1:8058/docs`다.

```powershell
Invoke-RestMethod http://127.0.0.1:8058/health
curl.exe --fail -sS -D off.headers.txt -F "file=@input.wav" -F "enabled=false" http://127.0.0.1:8058/denoise -o off.wav
curl.exe --fail -sS -D on.headers.txt -F "file=@input.wav" -F "enabled=true" http://127.0.0.1:8058/denoise -o on.wav
```

`POST /denoise`는 `multipart/form-data`의 `file`과 `enabled`를 받는다. 두 조건은 동일한 채널 변환과 리샘플링을 사용한다. 출력은 16kHz 모노 float32 WAV다. 헤더 `X-Denoise-Applied`, `X-Strength`, `X-Inference-Seconds`에서 적용 상태와 시간을 확인할 수 있다. 요청당 최대 60초 및 파일 25MiB를 처리한다. STT 담당이 두 결과를 같은 음성 인식 설정으로 비교하면 된다.

통합 전에는 옵션 기본값 OFF를 권장한다. 실제 주문 녹음에서 메뉴·수량·온도와 처리 시간의 차이를 확인해 적용 범위를 정한다.

## API 점검 재현

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe verify_api.py
```

검증은 로컬에서 만든 짧은 파형을 사용하므로 AI Hub 음성 파일이 필요 없다.
