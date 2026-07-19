# Kaven Release Notes

버전 관리 정책: 모든 업데이트 시 버전을 올리고(`0.0.01`부터 시작), 릴리스 노트/알림 헤더/로그 메타데이터에 동일 버전을 표시합니다.

---

## v0.0.10 — 2026-07-19

### 핵심: README 전면 재작성 + 실제 스크린샷 갤러리

1. **README.md 전면 재구성** (문서 전용 릴리스, 코드 변경 없음)
   - 스크린샷 갤러리 → 목차 → 기능/아키텍처/빠른시작/콘솔/에이전트/설정/
     API/구조/테스트/운영 순서로 재편
   - 버전별 변경 이력 나열을 제거하고 `docs/release-notes.md` 링크로 일원화
   - 아키텍처 다이어그램(수집→게이팅→분석→dedup→경보/로그/opt-in 업로드,
     코어→웹/MCP 어댑터 계층) 추가
   - 환경변수 표, API 요약 표, 단축키 표, 프로젝트 구조 트리 정리
   - OpenSky 인증 안내를 현행 OAuth2(`OPENSKY_CLIENT_ID/SECRET`) 기준으로 갱신
2. **스크린샷 7종 추가** (`docs/images/*.png`)
   - cop / feed / intel / assets / system / palette / help
   - 데모 데이터(7개 지역·7건 이벤트)로 실제 콘솔을 Playwright 캡처
   - 오프라인 SVG 그리드 모드 캡처임을 README에 명시 (온라인은 다크 타일맵)

### 검증 결과
- 문서 전용 변경: `ruff check .` 통과, `pytest` 이전과 동일 (58 passed)

---

## v0.0.09 — 2026-07-19

### 핵심: 3-렌즈(정확성·보안·프론트엔드) 검증에서 발견된 14건 수정

머지 전 브랜치 전체 diff(v0.0.06–08)를 세 관점의 독립 리뷰로 검증하고
확인된 결함을 전부 수정.

**정확성 렌즈 (3건)**
1. MED `kaven.py` — `KAVEN_LOG_DIR`이 읽기에만 적용되고 쓰기(`run_once`)는
   하드코딩 경로 사용 → 읽기/쓰기 모두 `log_store.default_log_dir()` 사용으로 통일
2. LOW `mcp_server.py` — id 없는 요청(notification)에 `id:null` 응답 발생
   → JSON-RPC 2.0 규격대로 무응답 처리
3. LOW `agent_service.py` — `limit=0`이 1건을 반환 → 0건(카운터만) 반환

**보안 렌즈 (3건)**
4. MED `index.html` — `source_url`의 `javascript:` 스킴이 href로 그대로 렌더링
   (외부 뉴스/LLM 출력 유래 XSS) → http/https만 링크화, 그 외 텍스트 표시
5. MED `mcp_server.py` — stdin으로 비객체 JSON(`5`, `[]`) 수신 시 루프 크래시
   → `-32600 invalid request` 응답으로 보호
6. LOW `mcp_server.py` — `date` 인자 미검증(HTTP 라우터와 비대칭)
   → 동일한 YYYYMMDD 검증 적용

**프론트엔드 렌즈 (8건)**
7. MED — SSE (재)연결 직후 가짜 "NEW RUN INGESTED" 토스트+리로드
   → run_id 추적으로 첫 스냅샷/중복 무시
8. MED — `selectRegion` 히스토리 fetch 레이스(늦은 응답이 다른 선택 덮어씀)
   → await 후 선택 일치 검사
9. MED — `/guide` 실패 시 스파크라인 "LOADING…" 영구 고착
   → "HISTORY UNAVAILABLE" 표시
10. MED — 백엔드 다운 시 60초마다 에러 토스트 스팸
    → 상태 전환 시에만 토스트(다운/복구 각 1회)
11. LOW — Run/새 run 후 Intel 날짜 목록 캐시 미무효화 → 무효화 추가
12. LOW — System 뷰 중복 `style` 속성 → 병합
13. LOW — 전 지역 quiet일 때 보이지 않는 토글이 상태를 바꾸던 문제 → 가드
14. LOW — 필터 복원 값이 옵션에 없으면 셀렉트가 빈 표시 → ALL로 복귀

### 검증 결과
- `ruff check .` → All checks passed
- `pytest` → 58 passed (+회귀 테스트 4건: MCP non-dict/notification/date 검증,
  limit=0), 기존 log replay 실패 1건 동일
- 브라우저 확인: LIVE 연결 8초간 가짜 토스트 0건, 스파크라인 정상 렌더링
- `KAVEN_LOG_DIR` 설정 시 쓰기 경로가 env를 따르는 것 확인

---

## v0.0.08 — 2026-07-18

### 핵심: Ops Console 운영 능률(UX efficiency) 리뷰·조정

프론트엔드(`webapp/frontend/index.html`) 사용성 리뷰에서 찾은 비효율을 개선.
백엔드 변경 없음.

1. **전역 키보드 단축키** (마우스 의존 제거)
   - `1`–`5` 뷰 전환, `Ctrl+K`/`/` 커맨드 팔레트, `J`/`K` 다음·이전 이벤트
     (현재 피드 필터·정렬 순서 기준, 피드에서 선택 행 자동 스크롤)
   - `F` Feed 이동+텍스트 필터 포커스, `R` 수집 1회 실행, `L` LIVE 토글
   - `Esc` 선택 해제/오버레이 닫기, `?` 단축키 도움말 오버레이 (레일 버튼도 추가)
   - 입력 필드 포커스 중에는 단축키 비활성 (오입력 방지)
2. **상태 지속성 (localStorage)**
   - 마지막 뷰, 피드 필터(severity/카테고리/신호/텍스트), 정렬 기준,
     LIVE 상태, 조용한 AO 표시 여부를 저장하고 새로고침 시 복원
3. **데이터 신선도 표시**
   - 상단바 `SYNC nS AGO` 매초 갱신, 90초 초과 시 경고색 — 스트림 끊김을
     즉시 인지 가능
4. **워치리스트 스캔 노이즈 감소**
   - severity 0·이벤트 0 지역은 기본 접힘, `+n QUIET` 토글로 펼침
     (데이터가 아예 없는 날은 전체 표시 유지)
   - 자산 행 클릭 → Feed로 전환 + 해당 자산명 필터 자동 적용 (조사 동선 단축)
5. **피드 정렬**
   - Time/Sev 헤더 클릭으로 정렬 컬럼/방향 토글 (▾/▴ 인디케이터)
6. **인스펙터**
   - 헤더 `‹`/`›` 버튼(또는 J/K)으로 이전·다음 이벤트 순회
   - `⧉ JSON` 버튼: 선택 이벤트 전체 필드를 클립보드로 복사
7. **커맨드 팔레트 액션 추가**
   - "Copy ops briefing (LLM context)": `/agent/context` 응답의 마크다운
     브리핑을 클립보드로 복사 — 에이전트/보고서 워크플로 연결

### 검증 결과
- Playwright(Chromium) E2E: 키보드 내비게이션(J/K 선택·2번 키 뷰 전환),
  Sev 정렬, 도움말 오버레이, QUIET 토글(3→9행), 자산 클릭 필터(WTI 1행),
  새로고침 후 뷰·필터 복원, SYNC 인디케이터 — 전부 통과, 콘솔 에러 0
- `ruff check .` / `pytest` — 백엔드 변경 없음, 이전과 동일 (54 passed)

---

## v0.0.07 — 2026-07-18

### 핵심: AI 에이전트 연동 계층 + 코어/HTTP 전반 리팩토링

1. **MCP 서버** (`src/kaven/mcp_server.py`, 신규)
   - 외부 SDK 의존성 없는 stdio MCP 서버 (개행 구분 JSON-RPC 2.0 직접 구현)
   - 도구 8개: `kaven_ops_summary`, `kaven_events`, `kaven_agent_context`,
     `kaven_region`, `kaven_daily_report`, `kaven_portfolio`, `kaven_config`,
     `kaven_run_collection`
   - 등록: `claude mcp add kaven -- python -m src.kaven.mcp_server`
   - heavy import(수집기 체인)는 `kaven_run_collection` 호출 시점에만 지연 로드
2. **에이전트 REST API** (`/agent/*`, 신규)
   - `GET /agent/manifest` — 엔드포인트/MCP 도구/스키마 어휘(지역 코드,
     카테고리, 신호, severity 의미) 기계가독 카탈로그
   - `GET /agent/context` — LLM 프롬프트 주입용 압축 마크다운 브리핑
     (`date`, `max_events`, `severity_min`)
   - `GET /agent/events` — run 중첩 없는 평탄화 이벤트 쿼리
     (severity/지역/카테고리/신호/키워드 필터 + 중복 제거 + 좌표/ID enrichment)
3. **전반 리팩토링 — 코어와 HTTP 계층 분리**
   - `src/kaven/log_store.py` 신규: JSONL 로그 탐색/파싱/중복제거 단일 소스
     (app.py·report_generator·ops에 3중복이던 로직 통합), `KAVEN_LOG_DIR` env 지원
   - `src/kaven/regions.py` 신규: 지역 좌표/한글명/설명 + 스키마 어휘 단일 소스
   - `src/kaven/ops_summary.py`: `webapp/backend/ops.py`에서 코어로 이동
     (+`enrich_event` 공용화)
   - `src/kaven/aggregates.py` 신규: 가이드/지도/포트폴리오 집계 (app.py에서 이동)
   - `src/kaven/agent_service.py` 신규: 이벤트 쿼리·컨텍스트·매니페스트
   - `webapp/backend/app.py` 436줄 → 40줄 (앱 조립만), 엔드포인트는
     `webapp/backend/routers/{system,runs,ops,agent,intel,portfolio}.py`로 분리
   - webapp import 시 수집기 의존성(feedparser 등)이 더 이상 필요 없음
     (`run_once`는 `POST /runs/once` 호출 시점 지연 로드)
4. **버그 수정**
   - `/report/dates`가 `/report/{date}` 경로 파라미터에 먼저 매칭되어 항상
     400을 반환하던 라우트 순서 버그 수정 → Intel 뷰 날짜 목록 정상화
   - `GET /runs/dates` 신규 (로그 존재 날짜 목록)
5. **테스트**
   - `tests/test_log_store.py` 7건, `tests/test_agent_service.py` 6건,
     `tests/test_mcp_server.py` 7건 신규. `test_ops_summary.py`는 이동된
     모듈 경로로 갱신

### 운영 영향
- 기존 REST API 경로/응답 변경 없음 (신규 엔드포인트만 추가)
- `webapp.backend.ops` 모듈은 `src.kaven.ops_summary`로 이동 (직접 import하던
  경우에만 경로 수정 필요)
- MCP 서버는 로그 디렉터리만 읽으므로 API 키 없이 동작 (`kaven_run_collection` 제외)

### 검증 결과
- `ruff check .` → All checks passed
- `python3 -m pytest -q` → 54 passed, 1 failed (기존 log replay 이슈, v0.0.06 노트 참조)
- uvicorn 구동 후 전 엔드포인트 curl 스모크 테스트 + MCP stdio 세션
  (initialize → tools/list → tools/call) E2E 확인 + 프론트 브라우저 리그레션 확인

---

## v0.0.06 — 2026-07-18

### 핵심: Palantir Maven 스타일 작전 콘솔(Ops Console) UX 전면 개편

`webapp/frontend/index.html`을 탭 기반 SPA에서 Maven Smart System 류의
다중 패널 인텔리전스 콘솔로 재설계.

1. **COP (Common Operating Picture)**
   - Leaflet + CARTO 다크 타일 기반 전술 지도
   - AIS(녹색)/ADS-B(청록) 감시구역 bounding box 오버레이 (비활성 구역은 흐리게)
   - 지역별 severity 마커: 크기·색상 스케일, severity ≥ 4는 펄스 링 애니메이션
   - 지도 하단 24시간 이벤트 타임라인 스트립 (UTC 축, 클릭 → 인스펙터)
   - CDN 불가(오프라인) 시 SVG 격자 지도로 자동 폴백
2. **3-패널 워크스페이스**
   - 좌측 아이콘 레일: COP / Event Feed / Intel Report / Asset Impact / System
   - 좌측 워치리스트: AO(감시 지역) severity 정렬 목록 + 영향 자산 목록
   - 우측 인스펙터: 이벤트 상세(메타 테이블·분석 근거·출처 링크·지도 이동),
     지역 도시에(설명·7일 severity 스파크라인·당일 이벤트 목록)
3. **커맨드 팔레트** (`Ctrl+K` 또는 `/`)
   - 지역·이벤트·자산·뷰·액션 통합 검색, 키보드 내비게이션
4. **상단 커맨드 바**
   - THREATCON 레벨(당일 최대 severity), RUNS/EVENTS/UNIQUE 카운터
   - UTC/KST 실시간 시계, LIVE(SSE) 토글, Run Collection 버튼, 토스트 알림
5. **백엔드**
   - `GET /ops/summary` 신규 (`webapp/backend/ops.py::build_ops_summary`)
     — 지역 상태 + 전체 이벤트(좌표·안정적 ID 포함) + 자산 영향 + 감시구역
     단일 payload. `?date=YYYYMMDD` 지원.
   - `REGION_COORDS`를 `ops.py`로 이동, `app.py`는 alias로 하위호환 유지
6. **테스트**
   - `tests/test_ops_summary.py` 7건 신규 (빈 날짜, 좌표/ID 부여, 지역 정렬,
     자산 집계, dedup, watchzone 포함, 미등록 지역 안전 처리)

### 운영 영향
- Breaking change 없음: 기존 API 전부 유지, 신규 엔드포인트만 추가
- 프론트 접속 방법 동일 (`http://127.0.0.1:8080`), API 주소는 `?api=` 쿼리로 override 가능
- 지도 타일은 CARTO CDN 사용(브라우저에서 로드). 오프라인 환경에서는 SVG 폴백 동작

### 검증 결과
- `ruff check .` → All checks passed
- `python3 -m pytest -q` → 34 passed, 1 failed
  (실패 1건은 기존 `test_kaven_log_replay_integration.py` — v0.0.05 저장소 위생 작업으로
  운영 로그 `logs/maven_20260403.jsonl`가 추적 해제되어 발생하는 기존 이슈, 본 변경과 무관)

---

## v0.0.05 — 2026-07-03

### 핵심: 입력기준 중복제거(input-gating)로 알림 노이즈 제거
운영 중 동일 사건이 표현만 바뀌어 5분마다 반복 발송되던 문제를 근본 수정.

1. **LLM 호출 게이팅** (`kaven.py`)
   - `_trigger_signatures()` / `_new_trigger_signatures()` / `_record_seen_inputs()` 신규
   - 새 자극(신규 뉴스 URL, anomaly 있는 AIS/ADS-B)이 없으면 LLM 분석·발송을 통째로 스킵
   - 자극 시그니처: 뉴스=url(없으면 title), AIS/ADS-B=`zone+anomaly+규모버킷(10단위)`
   - `sent_cache.json`에 `seen_inputs` 기록, 발송이 없어도 보존
2. **source_url 전파** (`analyzer.py`)
   - `_summarize_data()`가 LLM 입력에 뉴스 `url` 포함 → 출력 `source_url`이 채워짐 → URL 기반 dedup 복구
3. **fingerprint 정밀화** (`kaven.py` `_content_fingerprint`)
   - 키에 `region` 추가 → URL 없는 서로 다른 severity 5 사건이 한 지문으로 뭉개지던 문제 해소
4. **응답 파싱 견고화** (`analyzer.py` `_parse_analysis_response`)
   - 널바이트 제거, 균형 괄호 매칭으로 JSON 후보 추출 → 로컬/외부 LLM 출력 편차에 견고

### 저장소 위생
- 과거 커밋되어 추적되던 운영 데이터 추적 해제: `logs/maven_*.jsonl` 20건 + `sent_cache.json`
  - `.gitignore` 규칙 추가 이전 커밋분이 계속 추적되던 상태를 정리
  - 항상 dirty로 잡히던 `sent_cache.json`이 자동 동기화를 중단시키던 원인 제거

### 수집기
- **OpenSky**: Basic Auth 폐지 대응, OAuth2 client_credentials(`OPENSKY_CLIENT_ID`/`OPENSKY_CLIENT_SECRET`)로 Bearer 토큰 인증 복원 (`adsb_collector.py`)

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
