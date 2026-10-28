# Yareureong-Yareureong-Yareureong

## 고령자를 위한 LLM 기반 대화형 음성 주문 키오스크

고령 사용자의 키오스크 이용 편의성을 높이기 위해  
**터치 입력과 자연어 음성 주문을 함께 지원하는 대화형 주문 키오스크 프로토타입**을 개발합니다.

음성 입력은 잡음 제거, STT, LLM 기반 주문 해석을 거쳐 구조화된 주문 정보로 변환되며,  
Spring Boot Backend와 MariaDB를 통해 메뉴·가격·옵션을 검증한 뒤 사용자 확인을 거쳐 주문을 확정합니다.

---

## 주요 기능

- 터치 기반 키오스크 주문
- 자연어 음성 주문
- 잡음 제거 적용 / 미적용 비교
- STT 기반 음성 → 텍스트 변환
- LLM 기반 주문 정보 추출
- 메뉴명 / 수량 / 온도 / 옵션 구조화
- 주문 추가 / 수정 / 취소
- 누락 정보 및 모호한 요청 재질문
- MariaDB 기반 메뉴·가격·옵션 검증
- 화면 + TTS 주문 재확인
- 사용자 최종 승인 후 주문 확정

---

## System Architecture

```text
Voice Input
    ↓
Noise Reduction
    ↓
STT
    ↓
LLM
    ↓
Structured Order JSON
    ↓
Spring Boot Backend
    ↕
MariaDB
    ↓
Screen + TTS
    ↓
User Confirmation
```

터치 입력은 LLM을 거치지 않고 Backend로 직접 전달합니다.

```text
Touch Input
    ↓
Spring Boot Backend
    ↕
MariaDB
```

LLM은 사용자의 자연어 주문을 해석하는 역할만 담당하며,  
실제 메뉴·가격·옵션 검증과 주문 상태 변경은 Backend에서 수행합니다.

---

## Tech Stack

### AI / Data
- Python
- Whisper-based STT
- LLM
- RNNoise / DeepFilterNet
- FastAPI

### Backend
- Java
- Spring Boot
- REST API

### Database
- MariaDB

### Frontend
- HTML
- CSS
- JavaScript

### Collaboration
- Git
- GitHub

---

## Team

| Name | Role |
|---|---|
| 김민수 | AI / Data |
| 김지현 | Evaluation / QA |
| 이우혁 | Frontend / UI/UX |
| 이건호 | Backend / DB |

---

## Evaluation

프로젝트 성능은 다음 지표를 기준으로 평가할 예정입니다.

- 주문 필드 추출 정확도: 목표 90% 이상
- 복합·수정 주문 처리 성공률: 목표 85% 이상
- 음성 주문 완료율: 목표 90% 이상
- End-to-End 평균 응답시간: 목표 3초 이내
- 잡음 제거 적용 전·후 STT 및 주문 성능 비교
- 고령 사용자 대상 터치·음성 주문 사용성 비교

※ 위 수치는 개발 목표이며 실제 결과는 실험 후 기록합니다.

---

## Project Scope

### Included
- Web-based kiosk UI
- Touch ordering
- Voice ordering
- STT / LLM integration
- Menu DB validation
- Multi-turn order modification
- TTS confirmation

### Out of Scope
- Real card payment
- Commercial POS integration
- Dedicated telephone handset hardware
- Foundation model pre-training

---

## Development Status

> Planning / Architecture Design

현재 요구사항 정의와 시스템 아키텍처 설계를 진행하고 있습니다.

추후 개발 진행에 따라 실행 방법, API 명세, ERD 및 실험 결과를 업데이트할 예정입니다.
