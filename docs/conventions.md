# Project Conventions

본 문서는 팀 프로젝트의 코드 작성 및 Git Commit 규칙을 정의한다.

---

# 1. Commit Convention

기본 형식:

```text
type: description
```

예:

```text
feat: add STT transcription API
fix: correct order quantity validation
docs: update system architecture
```

## Commit Type

| Type | 설명 |
|---|---|
| feat | 새로운 기능 추가 |
| fix | 버그 수정 |
| docs | 문서 추가 및 수정 |
| refactor | 기능 변경 없는 코드 구조 개선 |
| test | 테스트 코드 추가 및 수정 |
| chore | 환경설정, 패키지, 기타 작업 |
| style | 코드 포맷 및 스타일 수정 |
| perf | 성능 개선 |

---

# 2. Branch Convention

기본 브랜치:

```text
main
```

개발 통합 브랜치:

```text
develop
```

기능 개발 브랜치:

```text
feature/기능명
```

예:

```text
feature/stt
feature/llm-order-parser
feature/order-api
feature/kiosk-ui
feature/evaluation
```

버그 수정:

```text
fix/기능명
```

예:

```text
fix/order-validation
```

---

# 3. Python Naming Convention

변수 및 함수:

```python
order_items = []
get_order_state()
```

snake_case를 사용한다.

Class:

```python
class OrderParser:
    pass
```

PascalCase를 사용한다.

상수:

```python
MAX_RETRY_COUNT = 3
```

UPPER_SNAKE_CASE를 사용한다.

---

# 4. Java Naming Convention

변수 및 Method:

```java
orderItems
getOrderState()
```

camelCase를 사용한다.

Class:

```java
OrderService
OrderController
```

PascalCase를 사용한다.

상수:

```java
MAX_RETRY_COUNT
```

UPPER_SNAKE_CASE를 사용한다.

---

# 5. API Naming

REST API 경로는 소문자와 복수형 명사를 기본으로 사용한다.

권장:

```text
GET /api/menus
POST /api/orders
PATCH /api/orders/{id}
DELETE /api/orders/{id}
```

지양:

```text
/getMenu
/createOrder
/deleteOrder
```

---

# 6. JSON Naming

JSON 필드는 snake_case를 기본으로 사용한다.

```json
{
  "menu_name": "아메리카노",
  "quantity": 2,
  "needs_clarification": false
}
```

Python AI Service와 Spring Boot 사이에서도 동일한 필드명을 사용한다.

---

# 7. 개발 원칙

- 한 Commit에는 하나의 논리적인 변경을 담는다.
- 다른 팀원의 코드를 이유 없이 대규모 수정하지 않는다.
- API 형식 변경 시 팀원에게 공유한다.
- API Key, DB Password 등 민감한 정보는 Commit하지 않는다.
- 실제 `.env` 파일은 GitHub에 업로드하지 않는다.
- 기능 구현 후 가능하면 간단한 테스트를 수행한 뒤 Push한다.
