# Kaven Release Notes

버전 관리 정책: 모든 업데이트 시 버전을 올리고(`0.0.01`부터 시작), 릴리스 노트/알림 헤더/로그 메타데이터에 동일 버전을 표시합니다.

---

## v0.0.05 — 2026-05-26

### 핵심: 입력기준 중복제거(input-gating)로 알림 노이즈 제거
운영 중 동일 사건이 표현만 바뀌어 5분마다 반복 발송되던 문제를 근본 수정.

1. **LLM 호출 게이팅** (`kaven.py`)
   - `_trigger_signatures()` / `_new_trigger_signatures()` / `_record_seen_inputs()` 신규
   - 새 자극(신규 뉴스 URL, anomaly 있는 AIS/ADS-B)이 없으면 **LLM 분석·발송을 통째로 스킵**
   - 자극 시그니처: 뉴스=url(없으면 title), AIS/ADS-B=`zone+anomaly+규모버킷(10단위)`
   - 군용기/선박 수가 버킷을 넘는 유의미한 변화는 재트리거 → 상황 악화는 놓치지 않음
   - `sent_cache.json`에 `seen_inputs` 기록, 발송이 없어도 보존
2. **source_url 전파** (`analyzer.py`)
   - `_summarize_data()`가 LLM 입력에 뉴스 `url` 포함 → 출력 `source_url`이 채워짐
   - URL 기반 출력단 dedup이 동반 복구
3. **fingerprint 정밀화** (`kaven.py` `_content_fingerprint`)
   - 키에 `region` 추가 → URL 없는 서로 다른 severity 5 사건이 한 지문으로 뭉개지던 문제 해소

### 저장소 위생
- 과거 커밋되어 박제돼 있던 운영 데이터 추적 해제: `logs/maven_*.jsonl` 20건 + `sent_cache.json`
  - `.gitignore`에는 이미 등록돼 있었으나 규칙 추가 이전 커밋분이 계속 추적되던 상태
  - **`sent_cache.json`이 항상 dirty로 잡혀 `upstream-sync.sh`의 자동 동기화를 중단시키던 원인 제거**

### 그간 반영분 정리 (v0.0.04 이후, 릴리스 노트 미기록분)
- 분석 엔진: claude -p CLI → OpenAI 호환 로컬 LLM(MLX)로 전환
- OpenSky: Basic Auth 폐지 대응 OAuth2 client_credentials로 복원
- 주간 upstream 자동 동기화 스크립트 + LaunchAgent 추가

### 테스트
- 기존 dedup/replay 테스트 통과, 입력 게이팅 스모크 검증 완료

---

## v0.0.04 — 2026-04-13

### 주요 변경사항 (설정 파일화 + Codex 리뷰 반영)
1. **감시 구역/피드/키워드 외부 설정화**
   - `src/kaven/config_loader.py` 신규: JSON 설정 로더, 내장 기본값 fallback
   - `src/kaven/config.example.json` 샘플 제공
   - 지원 섹션: `ais_zones`, `adsb_zones`, `news_feeds`, `news_keywords`, `social_keywords`
   - 각 항목에 `enabled` 플래그 → 선택적 활성화/비활성화
   - `KAVEN_CONFIG` 환경변수로 경로 override 가능
2. **4개 collector 리팩터링**
   - `ais_collector.py`: `WATCH_ZONES` → `_watch_zones()` (런타임 로드)
   - `adsb_collector.py`: `WATCH_AIRSPACES` → `_watch_airspaces()`
   - `news_collector.py`: `RSS_FEEDS`, `GEOPOLITICAL_KEYWORDS` → `_rss_feeds()`, `_geopolitical_keywords()`
   - `social_collector.py`: `SEARCH_KEYWORDS` → `_search_keywords()` + `SEARXNG_URL` env 정책 적용
3. **API 추가**
   - `GET /config` — 현재 로드된 설정 전체(enabled/disabled 수 포함) 조회
4. **Codex 리뷰 수정사항 반영 (PR #13에서 누락되었던 커밋 복원)**
   - ruff 11 errors → 0 (미사용 import 제거, 변수명 `l`→`line`, noqa 수정, `import re` 이동, W293 whitespace 정리)
   - `pyproject.toml` (ruff/mypy 설정)
   - `requirements.txt` / `requirements-dev.txt`
   - `social_collector` SearxNG URL 환경변수화 (P2)
5. **테스트**
   - `tests/test_config_loader.py` 신규 8건 (파일 없을 때 기본값, 커스텀 로드, enabled 필터, 전부 비활성, 오류 JSON 복원)
   - 전체: 28 passed

### 운영 영향
- Breaking change 없음: 기본 동작은 기존과 완전 동일
- 설정 커스터마이즈 원하면 `cp src/kaven/config.example.json src/kaven/config.json` 후 편집

### 검증 결과
- `ruff check .` → All checks passed
- `python3 -m pytest -q` → **28 passed**

### 관련 링크
- Issue: N/A (사용자 요청 + Codex handoff 이슈 대응)

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
