# Kaven WebApp 운영 체크리스트

## 사전 점검
- [ ] `pip install -r`(또는 필요한 패키지 수동 설치) 완료
- [ ] `.env` 값 확인 (`src/kaven/.env`)
- [ ] 로그 디렉터리 접근 권한 확인 (`src/kaven/logs/`)

## 백엔드 실행
- [ ] `uvicorn webapp.backend.app:app --reload --port 8000` 실행
- [ ] `GET /health` 200 확인
- [ ] `GET /runs` 응답 확인
- [ ] `GET /runs/stream` SSE 연결 확인

## 프론트 실행
- [ ] `python -m http.server 8080 --directory webapp/frontend` 실행
- [ ] 대시보드 페이지 로드 확인
- [ ] 필터(severity/category/keyword) 동작 확인
- [ ] 자동 폴링 ON/OFF 동작 확인
- [ ] SSE 실시간 업데이트 ON/OFF 동작 확인

## 런타임 검증
- [ ] Run Once 버튼으로 실행 트리거 확인
- [ ] 최신 이벤트 리스트 반영 확인
- [ ] 오류 발생 시 output 패널 로그 확인

## 배포 전
- [ ] `make test` 통과
- [ ] `make test-kaven` 통과
- [ ] 릴리즈 노트 업데이트 (`docs/release-notes.md`)
