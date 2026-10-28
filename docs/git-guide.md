# Git & GitHub Team Guide

본 문서는 캡스톤 프로젝트의 Git / GitHub 기본 사용 방법을 정리한다.

---

# 1. Repository Clone

처음 프로젝트를 받을 때:

```bash
git clone <repository-url>
```

프로젝트 폴더 이동:

```bash
cd Yareureong-Yareureong-Yareureong
```

---

# 2. 최신 코드 가져오기

작업 시작 전:

```bash
git pull
```

develop 브랜치를 사용하는 경우:

```bash
git checkout develop
git pull origin develop
```

---

# 3. Branch 확인

```bash
git branch
```

현재 브랜치는 `*`로 표시된다.

---

# 4. 새로운 기능 Branch 생성

예: STT 개발

```bash
git checkout develop
git pull origin develop
git checkout -b feature/stt
```

예: Backend 주문 기능

```bash
git checkout -b feature/order-api
```

---

# 5. 변경된 파일 확인

```bash
git status
```

---

# 6. 파일 Stage

전체 변경사항:

```bash
git add .
```

특정 파일:

```bash
git add 파일명
```

---

# 7. Commit

예:

```bash
git commit -m "feat: add STT transcription API"
```

문서 수정:

```bash
git commit -m "docs: update system architecture"
```

버그 수정:

```bash
git commit -m "fix: correct menu validation"
```

---

# 8. GitHub에 Push

처음 생성한 브랜치:

```bash
git push -u origin feature/stt
```

이후:

```bash
git push
```

---

# 9. Pull Request

기능 개발이 끝나면 GitHub에서 Pull Request를 생성한다.

기본 흐름:

```text
feature/*
    ↓
develop
    ↓
main
```

일반 기능 개발은 바로 main에 합치지 않는다.

---

# 10. 작업 시작 전 권장 순서

```bash
git checkout develop
git pull origin develop
git checkout feature/본인브랜치
```

필요한 경우 develop의 최신 변경사항을 자신의 브랜치에 반영한다.

---

# 11. 작업 종료 순서

```bash
git status
git add .
git commit -m "type: description"
git push
```

그 후 GitHub에서 Pull Request를 생성한다.

---

# 12. 주의사항

## .env 업로드 금지

다음과 같은 정보는 GitHub에 Commit하지 않는다.

```text
API KEY
DB PASSWORD
SECRET KEY
TOKEN
```

실제 값은 `.env`에 저장하고 `.env.example`에는 변수 이름만 공유한다.

---

## main 직접 Push 지양

초기 프로젝트 설정을 제외하고 실제 개발이 시작된 이후에는:

```text
feature branch
      ↓
Pull Request
      ↓
develop
      ↓
검증
      ↓
main
```

흐름을 사용한다.

---

# 13. 충돌 발생 시

Git 충돌이 발생하면 무작정 파일을 삭제하거나 강제 Push하지 않는다.

먼저 팀원에게 공유하고 충돌된 부분을 확인한 뒤 해결한다.

특히 다음 명령은 충분히 이해하지 않은 상태에서 사용하지 않는다.

```bash
git push --force
git reset --hard
```

공용 프로젝트의 다른 작업 기록을 잃을 수 있다.

---

# 14. 팀 Branch 예시

```text
main
└── develop
    ├── feature/ai-stt
    ├── feature/ai-llm
    ├── feature/evaluation
    ├── feature/frontend-ui
    └── feature/backend-order
```

담당 기능 단위로 Branch를 생성하여 개발한다.
