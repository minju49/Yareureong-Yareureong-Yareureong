# 봄카페 학교 서버

Linux x86-64 PC에서 Docker와 Docker Compose를 사용합니다. 배포 ZIP에는 팀의 메뉴 SQL, 실행용 Spring JAR, MariaDB와 Spring Docker 이미지가 들어 있습니다. 시연 전용 DB의 새 접속 정보는 첫 실행에서 생성합니다.

1. ZIP을 풀고 `bom-server-1124` 폴더에서 터미널을 엽니다.
2. `bash 1_prepare.sh`로 이미지 파일을 불러옵니다.
3. `bash 2_start.sh`로 Spring과 MariaDB를 켭니다.
4. `bash 3_check.sh`에서 `menu_count: 61`, `orders_table_ready: true`를 확인합니다. Windows 키오스크의 담당자 연결 설정에 Linux PC의 학교 LAN 주소와 표시된 포트를 입력합니다.
5. ZipEnhancer도 시험할 때 `bash 5_start_zip.sh`로 CPU 잡음 서버를 켭니다. 키오스크에서 잡음 서버 주소를 연결하고 ZipEnhancer를 골라 녹음합니다.

기본 Spring 포트는 8080, ZipEnhancer 포트는 8058입니다. 포트를 이미 사용하는 프로그램이 있으면 이 폴더의 `.env`에 `BOM_MENU_HTTP_PORT=18080` 또는 `BOM_NOISE_HTTP_PORT=18058`처럼 다른 포트를 지정하고 다시 시작합니다. MariaDB는 컨테이너 안에서 Spring과 통신합니다. 종료할 때 `bash 4_stop.sh`를 실행하면 시연 DB가 보존됩니다.

학교 Qwen3.5 9B는 Windows에서 학교 실험에 쓰던 주소로 호출합니다. Docker에는 메뉴·주문 서버와 선택 가능한 CPU ZipEnhancer가 들어 있습니다. CPU 잡음 서버의 지원 모드는 끄기와 ZipEnhancer입니다. GPU 잡음 서버를 같은 호스트에서 열 경우에는 포트가 겹치지 않도록 확인합니다.

메뉴 목록이나 앱 이름이 보이는 단계와 주문 저장까지 성공한 단계는 구분해서 확인하세요. `/api/menu-health`가 정상이면 Windows에서 직접 주문을 담고 결제 시연을 눌러 저장 번호를 확인합니다.

팀의 원본은 `backend/demo (2).zip`, `backend/menus_catalog.sql`, 루트의 `index.html`입니다. Spring 확장 코드는 `backend/menu-service`, 키오스크 연결 코드는 `ai/text-review/integration_demo`에 있습니다. 원본 메뉴 조회에 장바구니 검산과 시연 주문 저장을 추가했습니다.
