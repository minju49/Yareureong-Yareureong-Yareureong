# System Architecture

## Voice Order Flow

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

## Touch Order Flow

Touch Input  
↓  
Spring Boot Backend  
↕  
MariaDB  

## Design Principles

- LLM은 사용자의 자연어 주문을 해석한다.
- LLM은 메뉴명, 수량, 온도, 옵션, 주문 의도를 구조화된 JSON으로 변환한다.
- Spring Boot는 주문 상태와 비즈니스 로직을 관리한다.
- MariaDB는 메뉴, 가격, 허용 옵션, 주문 세션 정보를 관리한다.
- LLM은 MariaDB에 직접 접근하지 않는다.
- 실제 메뉴·가격·옵션 검증과 주문 상태 변경은 Spring Boot에서 수행한다.
- 터치 주문은 LLM을 거치지 않고 Backend로 직접 전달한다.
- 오류나 누락 정보가 발생하면 기존 주문 상태를 유지하고 재질문 또는 터치 입력으로 전환한다.
