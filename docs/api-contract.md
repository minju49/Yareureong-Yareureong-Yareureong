# AI - Backend API Contract

## 1. 목적

본 문서는 LLM 기반 음성 주문 시스템에서  
Python AI Service와 Spring Boot Backend 사이에 주고받는 데이터 형식을 정의한다.

AI Service는 사용자의 자연어 주문을 해석하여 구조화된 JSON을 반환한다.

실제 메뉴 존재 여부, 가격, 허용 옵션, 주문 상태 변경은 Spring Boot Backend와 MariaDB가 담당한다.

---

# 2. 전체 흐름

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
```

터치 입력의 경우 AI Service를 거치지 않는다.

```text
Touch Input
    ↓
Spring Boot Backend
    ↕
MariaDB
```

---

# 3. 주문 해석 API

## POST /ai/order/interpret

사용자의 텍스트와 현재 주문 상태를 이용하여 주문 의도를 분석한다.

### Request

```json
{
  "text": "아이스 아메리카노 두 잔 주세요.",
  "current_order": []
}
```

### Response

```json
{
  "intent": "ADD_ITEM",
  "items": [
    {
      "menu_name": "아메리카노",
      "quantity": 2,
      "temperature": "ICE",
      "options": []
    }
  ],
  "needs_clarification": false,
  "missing_fields": [],
  "clarification_question": null
}
```

---

# 4. Intent 정의

| Intent | 설명 |
|---|---|
| ADD_ITEM | 새로운 메뉴 추가 |
| UPDATE_ITEM | 기존 주문 수정 |
| REMOVE_ITEM | 특정 메뉴 삭제 |
| CANCEL_ORDER | 전체 주문 취소 |
| CONFIRM_ORDER | 주문 확인 |
| UNKNOWN | 의도를 판단하기 어려움 |

---

# 5. 재질문이 필요한 경우

예:

```text
사용자: 아메리카노 하나 주세요.
```

HOT / ICE 정보가 반드시 필요한 메뉴라고 가정할 경우:

```json
{
  "intent": "ADD_ITEM",
  "items": [
    {
      "menu_name": "아메리카노",
      "quantity": 1,
      "temperature": null,
      "options": []
    }
  ],
  "needs_clarification": true,
  "missing_fields": [
    "temperature"
  ],
  "clarification_question": "따뜻한 것으로 드릴까요, 차가운 것으로 드릴까요?"
}
```

AI가 누락된 값을 임의로 결정하지 않는다.

---

# 6. 모호한 수정 요청

예:

```text
현재 주문:
- 아이스 아메리카노 1잔
- 카페라떼 1잔

사용자:
"그거 하나 빼주세요."
```

대상이 불명확한 경우:

```json
{
  "intent": "REMOVE_ITEM",
  "items": [],
  "needs_clarification": true,
  "missing_fields": [
    "target_item"
  ],
  "clarification_question": "어떤 메뉴를 빼드릴까요?"
}
```

Backend는 사용자의 추가 확인 전까지 기존 주문 상태를 변경하지 않는다.

---

# 7. Backend 검증 원칙

AI Service가 반환한 데이터는 주문 확정 정보가 아니다.

Spring Boot Backend에서 다음 항목을 반드시 검증한다.

- 메뉴 존재 여부
- 메뉴 가격
- HOT / ICE 가능 여부
- 옵션 존재 여부
- 해당 메뉴에서 옵션 사용 가능 여부
- 주문 수량
- 현재 주문 상태
- 수정 및 삭제 대상 존재 여부

가격은 LLM이 생성하지 않는다.

Backend가 MariaDB의 가격 정보를 기준으로 계산한다.

---

# 8. 오류 처리

## AI Service Timeout

AI Service가 일정 시간 내 응답하지 않는 경우:

- 기존 주문 상태 유지
- 오류 메시지 반환
- 재시도 또는 터치 입력 안내

## 잘못된 JSON

JSON Schema를 만족하지 않는 경우:

- 주문 상태 변경 금지
- 해당 AI 응답 폐기
- 재요청 또는 사용자 재입력

## 존재하지 않는 메뉴

AI가 존재하지 않는 메뉴를 반환한 경우:

- MariaDB 검증 실패
- 주문에 추가하지 않음
- 사용자에게 다시 입력하도록 안내

---

# 9. 기본 원칙

1. LLM은 주문을 해석한다.
2. LLM은 DB에 직접 접근하지 않는다.
3. Backend가 주문 상태를 관리한다.
4. MariaDB가 메뉴·가격·옵션의 기준 데이터가 된다.
5. 사용자의 명시적인 확인 전에는 주문을 최종 확정하지 않는다.
