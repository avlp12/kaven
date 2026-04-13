# Kaven Release Notes

버전 관리 정책: 모든 업데이트 시 버전을 올리고(`0.0.01`부터 시작), 릴리스 노트/알림 헤더/로그 메타데이터에 동일 버전을 표시합니다.

---

## v0.0.03 — 2026-04-13

### 주요 변경사항 (대시보드 기능 확장)
1. **일일 분석 리포트 자동 생성** (`/report`)
   - `src/kaven/report_generator.py` 신규 모듈
   - JSONL 로그에서 이벤트 로드 → 중복 제거 → 지역/카테고리/자산별 집계 → 마크다운 브리핑 자동 생성
   - API 키 없이 순수 규칙 기반 동작
   - `GET /report` (오늘), `GET /report/{YYYYMMDD}` (과거), `GET /report/dates` (목록)
2. **인터랙티브 분쟁 지도** (`/map`)
   - globe.gl 3D 지구본에 `GET /map/data` API로 실시간 이벤트 표시
   - Severity별 색상 마커, 클릭 줌, 자동 회전
   - 기존 하드코딩 시각화를 API 기반으로 교체
3. **지역별 분쟁 현황 가이드** (`/guide`)
   - 9개 감시구역: 호르무즈, 대만, 한반도, 우크라이나, 인도·파키스탄, 남중국해, 홍해·예멘, 사헬, 전지구
   - `GET /guide` (전체 현황), `GET /guide/{region}?days=7` (상세 + 7일 히스토리)
4. **프론트엔드 전면 리뉴얼**
   - 단일 테이블 → 탭 기반 다크 테마 SPA (Dashboard / Report / Map / Guide)
   - Severity 뱃지, 통계 카드, 반응형 레이아웃, 지역 카드 그리드
5. **테스트 추가**
   - `tests/test_report_generator.py` 6건 (빈 날짜, 단일 이벤트, dedup, 다지역 정렬, 자산 집계, 카테고리 분포)

### 운영 영향
- Breaking change 없음 (기존 API 변경 없이 신규 엔드포인트만 추가)
- 웹 대시보드 접속 방법 동일: `http://127.0.0.1:8080`

### 검증 결과
- `python3 -m pytest -v` → **20 passed**
- `make test-kaven` → 통과

### 관련 링크
- PR: #12 (`Add daily report, interactive map, and region guide features`)
- Merge commit: `407b84d`

---

## v0.0.02 — 2026-04-11

### 주요 변경사항 (이슈 #7 대응)
1. **Convex 원격 업로드 정책을 opt-in으로 전환**
   - `CONVEX_SITE_URL` 환경변수 설정 시에만 이벤트 payload를 외부로 전송
   - 기본 동작: 외부 전송 완전 비활성화 (로컬 로그만 보존)
2. **하드코딩된 엔드포인트 제거**
   - `https://exciting-cod-257.convex.site/addMavenRun` 하드코딩 완전 삭제
   - `CONVEX_SITE_URL` + `CONVEX_EVENT_PATH`(기본 `/addKavenRun`) 동적 조합
3. **업로드 로직 리팩터링**
   - `src/kaven/kaven.py::_upload_remote_if_enabled()` 헬퍼로 분리
   - trailing/leading slash 정규화, 원격 실패 시 예외 전파 방지(로컬 로그 보존 우선)
4. **정책 회귀 테스트 추가**
   - `tests/test_kaven_convex_policy.py` (9건)
   - 소스 문자열 정적 검사로 하드코딩 엔드포인트 부재를 검증 → upstream sync 이후 회귀까지 차단
5. **개발 편의성**
   - `make test-kaven` 타깃에 convex policy 테스트 포함
   - `.gitignore` 신규 추가(`__pycache__/`, `.env`, `.port_sessions/` 등)
6. **버전 메타데이터 갱신**
   - `src/kaven/version.py`, User-Agent 헤더, 텔레그램 경보 헤더 모두 `v0.0.02`로 동기화

### 운영 영향 (Breaking Change)
- **기존**: 이벤트가 있으면 항상 하드코딩 Convex endpoint로 POST 시도
- **변경 후**: `CONVEX_SITE_URL` 명시 설정 시에만 POST (기본은 로컬 로그만 저장)
- 기존에 Convex 엔드포인트에 의존하던 배포는 해당 환경의 `.env`에 다음을 추가해야 합니다:
  ```
  CONVEX_SITE_URL=https://<your-convex>.convex.site
  CONVEX_EVENT_PATH=/addKavenRun
  ```

### 검증 결과
- `python3 -m pytest -q` → **14 passed** (convex policy 9 + dedup 4 + log replay 1)
- `make test-kaven` → 통과
- 기존 dedup/log replay 테스트 영향 없음
- 하드코딩 문자열 잔존 여부: `exciting-cod-257`, `addMavenRun` 모두 소스에 없음 (정적 테스트로 검증)

### 관련 링크
- Issue: #7
- PR: #9 (`Make Convex upload opt-in via CONVEX_SITE_URL`)
- Merge commit: `1d89500`

### 롤백
- 이전 태그/커밋으로 롤백 후 서비스 재시작
- 또는 `.env`에 `CONVEX_SITE_URL`만 설정해서 이전과 유사한 동작 복원 가능

---

## v0.0.01 — 2026-04-08

### 주요 변경사항 (초기 리브랜딩)
1. Maven → Kaven 리브랜딩 및 경로 정리 (`src/maven/` → `src/kaven/`)
2. dedup 로직 강화 (수치 토큰/소스 URL/동일 이벤트 판정)
3. 웹앱 스캐폴드 추가 (FastAPI API + 정적 대시보드)
4. 테스트/개발 편의성 개선 (`Makefile`, `pytest.ini`, `tests/test_kaven_dedup.py`, `tests/test_kaven_log_replay_integration.py`)
5. 실행 로그 파일명 전환 (`maven_YYYYMMDD.jsonl` → `kaven_YYYYMMDD.jsonl`, 구파일 읽기 호환 유지)
6. 텔레그램 경보 헤더/긴급 경보에 버전(`v0.0.01`) 표시
7. `/health` 응답과 런타임 로그 메타데이터에 버전 필드 포함

### 운영 영향
- 배포 시 `.env` 경로: `src/kaven/.env`
- 웹 백엔드 기본 포트: `8000`
- 정적 프론트 기본 포트: `8080`

### 검증 결과
- `make test`
- `make test-kaven`
- (선택) `python -m py_compile webapp/backend/app.py`

### 롤백
- 이전 태그/커밋으로 롤백 후 서비스 재시작
