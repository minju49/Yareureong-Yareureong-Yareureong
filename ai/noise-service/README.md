# 봄카페 잡음 처리 연결

이 서비스는 팀원이 전달한 잡음 제거 실험 코드로 16kHz 모노 PCM16 WAV를 처리합니다. 녹음 처리 조건과 선택된 모델을 결과에 기록합니다. 키오스크의 처음 선택은 끄기입니다.

- Linux CPU 시연은 `Dockerfile.cpu`로 준비한 이미지에서 ZipEnhancer를 실행합니다. 원래 실험의 모델과 처리 비율 0.25를 사용합니다.
- GPU 추가 실험은 Linux Python 3.11과 CUDA 12.8용 PyTorch를 실행할 수 있는 NVIDIA 환경에서 `bash 1_prepare_gpu.sh`와 `bash 2_start_gpu.sh`를 순서대로 실행합니다. 동봉한 모델 파일의 해시가 맞으면 가중치 다운로드를 생략합니다. Python 패키지 설치에는 인터넷이 필요합니다.
- GPU 모드에는 ZipEnhancer, MossFormerGAN, MossFormer2 SS 후 ZipEnhancer가 있습니다. 서비스 상태는 `/health`, 음성 처리는 `/api/process`로 확인합니다.

ZipEnhancer 가중치는 [ModelScope 공식 모델](https://modelscope.cn/models/iic/speech_zipenhancer_ans_multiloss_16k_base), MossFormer 가중치는 [MossFormerGAN](https://huggingface.co/alibabasglab/MossFormerGAN_SE_16K)과 [MossFormer2 SS](https://huggingface.co/alibabasglab/MossFormer2_SS_16K)에서 가져옵니다. 출처의 리비전과 가중치 해시는 `audio_lab/model_files.py`, `audio_lab/ensemble.py`, `audio_lab/speaker_separation.py`에서 확인할 수 있습니다.

학교에서 켠 서버의 주소를 키오스크 담당자 설정에 입력하세요. 선택한 모드의 실행에 실패하면 화면에 오류가 표시됩니다. 실행 기록에는 처리한 WAV와 다음 STT 결과가 저장됩니다.
