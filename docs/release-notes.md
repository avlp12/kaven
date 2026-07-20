# Kaven Release Notes

버전 관리 정책: 모든 업데이트 시 버전을 올리고(`0.0.01`부터 시작), 릴리스 노트/알림 헤더/로그 메타데이터에 동일 버전을 표시합니다.

---

## v0.0.18 — 2026-07-20

### 핵심: CLI 브리지 원클릭 OAuth 로그인

1. **Settings → 모델 공급자 CLI 카드에 연결(로그인) 버튼**
   - 설치된 CLI에만 표시. 클릭 시 백엔드 머신에서 해당 CLI의
     OAuth 로그인 플로우 실행:
     - 데스크톱(Windows/macOS/Linux 터미널 존재): **새 터미널 창**을 열어
       대화형 로그인(브라우저 오픈·디바이스 코드)을 그대로 완료
     - 헤드리스: 백그라운드 실행 후 초기 출력에서 **로그인 URL 추출** →
       콘솔이 새 탭으로 열어줌
2. **`POST /cli/{id}/login`** 신설 — 제공자별 로그인 명령 해석:
   `login_command` 필드(사용자 지정) → 알려진 기본값
   (claude→`claude`, codex→`codex login`, cursor→`cursor-agent login`,
   gemini→`gemini`) → 실행 바이너리. 미설치 400, 미등록 404
3. `cli_providers` 저장 검증기가 `login_command` 필드 보존 (shlex 검증)
4. **테스트**: +3건 (로그인 명령 해석 우선순위, 헤드리스 URL 추출,
   엔드포인트 200/404/400)

### 운영 영향
- Breaking change 없음. 로그인 명령 실행은 기존 CLI 브리지와 동일한
  신뢰 모델(사용자가 설정한 명령을 백엔드 머신에서 실행)
- 원격 서버에 콘솔만 띄운 경우 터미널 창은 서버 쪽에 열림 — 헤드리스
  URL 방식이 동작하지 않는 CLI는 서버에서 직접 로그인 필요

### 검증 결과
- `ruff check .` → All checks passed / `pytest` → 82 passed (기존 실패 1건 동일)
- 브라우저 E2E: 설치된 CLI(claude)에만 연결 버튼 렌더링, 콘솔 에러 0.
  엔드포인트는 가짜 CLI 스크립트로 URL 추출까지 pytest 검증

---

## v0.0.17 — 2026-07-20

### 핵심: 기본 뉴스 피드 확장 — 무료·페이월 없는 공개 소스 9종 추가

1. **기본 뉴스 피드 9종 추가** (전부 무료·페이월 없음, RSS 공개)
   - Al Jazeera English, Guardian World, DW(Deutsche Welle), France 24,
     UN News, CNA(Channel NewsAsia), gCaptain(해운·해사),
     OilPrice(에너지), Google News Top Stories
   - 해운(gCaptain)·에너지(OilPrice)는 AIS/호르무즈·WTI 감시 축과 직접 연관
2. **죽은 피드 정리**: Reuters 공식 RSS(feeds.reuters.com)는 2020년 서비스
   종료 — 기본 `enabled: false`로 전환 (이름에 종료 표기, 행은 보존)
3. OEC(oec.world) 검토: 뉴스 매체가 아닌 무역 데이터 시각화 플랫폼으로
   공개 뉴스 RSS가 없어 뉴스 수집기 기본 피드로는 미추가
   (Settings → 뉴스 피드에서 임의 RSS URL은 언제든 추가 가능)

### 운영 영향
- Breaking change 없음 — `config.json`에 `news_feeds`를 이미 저장(override)한
  경우 저장본이 우선하므로 기본값 변경이 자동 적용되지 않음
  (Settings → 뉴스 피드에서 직접 추가하거나 override 제거)
- 실패하는 피드는 수집기가 건너뛰므로 일부 피드 장애 시에도 동작 동일

### 검증 결과
- `ruff check .` → All checks passed / `pytest` → 79 passed (기존 실패 1건 동일)
- 참고: 원격 실행 환경의 네트워크 정책상 피드 URL 라이브 검증은 불가 —
  장기 운영 중인 공개 RSS 엔드포인트 기준으로 선정

---

## v0.0.16 — 2026-07-20

### 핵심: AO(감시 지역) 사용자 추가 — 발견성 + 분석기 완전 연동

1. **워치리스트에서 AO 바로 추가**
   - AREAS OF OPERATION 헤더에 `＋` 버튼 신설 → 클릭 시 Settings의
     감시 지역(AO) 편집 탭으로 바로 이동 (행 추가 → 저장 → 즉시 반영)
   - 툴팁 다국어(ko/en) 지원
2. **분석기(LLM) 지역 어휘 동적화**
   - 분석 프롬프트의 region 코드 목록이 하드코딩(내장 9개)이어서
     사용자가 추가한 AO에는 이벤트가 분류되지 않던 문제 수정
   - `build_user_prompt()` — 설정된 AO 기반으로 `코드|…|other` 어휘와
     `이름=코드` 매핑을 동적 생성 (비활성 지역 제외). OpenAI 호환·Gemini·
     Anthropic·CLI 브리지 5개 호출 경로 모두 적용
   - 이제 AO 추가만으로 지도·워치리스트·에이전트 어휘·LLM 분류가
     전부 자동 연동
3. **테스트**: +1건 (커스텀 AO가 프롬프트 어휘에 반영/비활성 제외/기본값 유지)

### 운영 영향
- Breaking change 없음 — AO 미커스터마이징 시 기존 내장 9개 지역과 동일 동작

### 검증 결과
- `ruff check .` → All checks passed / `pytest` → 79 passed (기존 실패 1건 동일)
- 브라우저 E2E: `＋` 클릭 → Settings 감시 지역 탭 활성, 발트해 AO 추가·저장 →
  `/ops/summary` 지역 목록·워치리스트(QUIET 토글) 반영, 콘솔 에러 0

---

## v0.0.15 — 2026-07-20

### 핵심: 지도 렌더링 수정 + 설정 UI에서 모델 키·토큰 직접 입력 + 가독성 개선

1. **월드맵 반자오선(경도 180°) 렌더링 수정**
   - 경도 180°를 가로지르는 폴리곤(러시아·알류샨 열도·피지)이 지도 전폭을
     가로지르는 수평 밴드로 깨져 보이던 문제 수정
   - 링 내 연속 점의 경도 점프(>180°)를 ±360° 시프트로 연속화 (`unwrapAntimeridian`)
2. **모델 자격증명 UI 입력** — Settings → 모델 공급자 카드에서 직접 설정
   - Anthropic(API 키/OAuth 토큰/Base URL/모델), OpenAI 호환(Base URL/키/모델),
     Gemini(키)를 카드에서 입력·저장, 연결 해제 버튼으로 삭제
   - `PUT /config/credentials` 신설 — config.json `credentials` 키에 저장
     (허용 키 화이트리스트, base URL http(s) 검증, 응답에 비밀값 미포함)
   - 우선순위: 환경변수 → UI 저장 자격증명. `GET /config` 응답에는 미노출,
     `/health` `analysis.stored`로 저장 여부만 boolean 노출 (placeholder 표시용)
   - analyzer/anthropic_auth가 `env_or_credential()`로 통일 해석
3. **UI 가독성 개선**
   - 전역 텍스트 대비 상향 (`--muted`/`--dim` 밝기 증가)
   - 설정 화면 한글 안내문을 mono·자간 스타일에서 산세리프 `note-text`
     (12.5px, 행간 1.65)로 교체 — 공급자 카드 본문/배지/내비/라벨 크기 확대
4. **테스트**: +2건 (자격증명 저장·삭제·env 우선순위·resolve_auth 연동,
   PUT /config/credentials 검증·/health 반영·GET /config 비노출)

### 운영 영향
- Breaking change 없음 — 환경변수 방식은 종전과 동일하게 우선 적용
- UI로 저장한 키는 서버 config.json에 평문 저장 (로컬 전용 권장, 문서화)

### 검증 결과
- `ruff check .` → All checks passed / `pytest` → 78 passed (기존 실패 1건 동일)
- 브라우저 E2E: 월드 줌 지도 밴드 소멸 확인, Gemini 키 저장→API Key 배지·
  '저장됨' placeholder·연결 해제 round-trip, 잘못된 base URL 400 토스트,
  콘솔 에러 0

---

## v0.0.14 — 2026-07-19

### 핵심: 구독(OAuth) 모델 연결 + zcode 스타일 설정 UI

1. **Anthropic 구독/OAuth 인증** (`src/kaven/anthropic_auth.py`)
   - 우선순위: `ANTHROPIC_API_KEY`(x-api-key) → `ANTHROPIC_AUTH_TOKEN`
     (Bearer + `anthropic-beta: oauth-2025-04-20`) → `ant` CLI 프로필
     (`ant auth print-credentials`, 240초 캐시)
   - Claude Pro/Max 구독자는 API 키 없이 `ant auth login`만으로 분석 모델 사용
   - `ANTHROPIC_BASE_URL`로 GLM(지푸)·Kimi 등 Anthropic 호환 엔드포인트 지원,
     기본 모델 `claude-sonnet-5` (`ANTHROPIC_MODEL`로 변경)
2. **CLI 구독 브리지** (`src/kaven/cli_providers.py`)
   - 구독(OAuth) 로그인된 공식 CLI에 분석 위임: Claude Code CLI(Pro/Max),
     OpenAI Codex CLI(ChatGPT Plus/Pro), Cursor Agent CLI, Gemini CLI
   - `config.json` `cli_providers` 섹션으로 커스터마이즈 (Grok 등 임의 CLI 등록
     가능), `KAVEN_CLI_PROVIDER`(auto/off/특정 id) 선택자
   - 분석 폴백 체인에 편입: OpenAI 호환 → Gemini → Anthropic → CLI 브리지
     → 규칙 기반
3. **zcode 스타일 설정 UI 재설계**
   - 좌측 설정 내비게이션(콘솔/모델/수집·데이터 그룹) + 우측 콘텐츠 페인,
     선택 탭 localStorage 유지
   - **모델 공급자 패널**: Direct API 카드(Anthropic·OpenAI 호환·Gemini —
     상태 점, OAuth·구독/API Key/미설정 배지, 엔드포인트·모델·환경변수 안내)
     + CLI 브리지 카드(설치됨/미설치/비활성 배지, 인라인 이름·명령 편집,
     사용 토글, 공급자 추가/해제/저장)
4. **상태 노출**: `/health`에 `analysis` 필드 (자격증명 값 미노출 —
   openai_compatible/gemini/anthropic 모드/anthropic_base_url/CLI 설치 여부),
   System 뷰 SERVICE STATUS에 분석 백엔드 상태 표시
5. **테스트**: +10건 (인증 우선순위·OAuth 헤더·ant CLI 캐시,
   CLI 선택자·실행·실패 처리, /health analysis, cli_providers 검증·저장)

### 운영 영향
- Breaking change 없음 — 자격증명 미설정 시 기존 규칙 기반 분석 그대로 동작
- API 키 방식(`ANTHROPIC_API_KEY` 등)은 종전과 동일하게 우선 적용

### 검증 결과
- `ruff check .` → All checks passed / `pytest` → 76 passed (기존 실패 1건 동일)
- 브라우저 E2E: 설정 내비 9개 탭 전환, 공급자 카드 7종(OAuth·구독 배지,
  설치됨/미설치 상태 점), CLI 브리지 이름 편집→저장 round-trip,
  탭 선택 새로고침 유지, EN/KO 전환, System 뷰 ANTHROPIC AUTH=OAUTH 표시,
  콘솔 에러 0

---

## v0.0.13 — 2026-07-19

### 핵심: Settings 전면 확장 — 서버 설정 전 섹션 + 콘솔 환경설정 커스터마이징

1. **서버 설정(config.json) 전 섹션 편집기** (스키마 기반 범용 편집기)
   - 편집 가능: `assets`, `regions`(신규 섹션), `ais_zones`, `adsb_zones`,
     `news_feeds`, `news_keywords`, `social_keywords`
   - 접이식 섹션 UI(활성/전체 카운트), 행 추가/삭제, 저장 시 즉시 반영
   - `PUT /config/{section}` 범용화 (v0.0.12의 `PUT /config/assets` body도
     하위호환 수용). 섹션별 검증: 좌표 범위·min<max, URL http(s) 스킴,
     자산 유형 화이트리스트, 식별자 중복 금지, 빈 행 무시
2. **감시 지역(regions) 설정화**
   - `config.json` `regions` 섹션 신설 (기본값: 내장 9개 지역)
   - `regions.region_info()` — 설정 우선 로드, `enabled:false` 지역은
     지도/워치리스트/가이드에서 숨김(이벤트 지역명 lookup은 유지)
   - ops/aggregates/agent manifest vocabulary가 설정 기반으로 동적 반영
     → 사용자 정의 AO 추가 가능
3. **콘솔 환경설정 (localStorage)**
   - 시작 화면(마지막 사용/특정 뷰), 자동 새로고침 주기(30s–5m/끄기),
     지도·타임라인 최소 severity 필터, 감시구역 오버레이 표시,
     고심각도 펄스 애니메이션, API 엔드포인트(저장 시 새로고침)
4. **테스트**: +2건 (커스텀 region이 ops에 반영/비활성 숨김,
   섹션 검증 로직 — zone 좌표 순서, feed URL 스킴, region code slug)

### 운영 영향
- Breaking change 없음 — 모든 섹션 미설정 시 기존 기본값과 동일 동작
- `PUT /config/assets`(구 body 형식) 하위호환 유지

### 검증 결과
- `ruff check .` → All checks passed / `pytest` → 66 passed (기존 실패 1건 동일)
- 브라우저 E2E: 7개 섹션 편집기 렌더링, regions 9행 편집, news_feeds 저장
  round-trip 토스트, minSev=4 설정 시 지도 마커 13→3·타임라인 3점,
  감시구역 오버레이 토글, 새로고침 후 환경설정 유지, 웜 상태 콘솔 에러 0

---

## v0.0.12 — 2026-07-19

### 핵심: Settings 뷰 신설 — 추적 자산 커스터마이징 + 한국어/영어 전환

1. **추적 자산 커스터마이징**
   - `config.json`에 `assets` 섹션 신설 (기본값 내장: WTI/KOSPI/원달러 등 8종)
   - `src/kaven/config_loader.py`: `DEFAULT_ASSETS`, `get_assets()`,
     `update_config_section()` (특정 섹션만 갱신, 다른 override 보존)
   - `aggregates.asset_meta()`: 하드코딩 `ASSET_META` 상수 → 설정 기반 로드
   - `enabled: false` 자산은 포트폴리오/ops 집계에서 제외,
     미등록 자산은 기존처럼 `type: other`로 표시
   - `PUT /config/assets` 신설 (검증: 이름 필수/중복 금지, 유형 화이트리스트,
     최대 100개) — Settings 뷰의 저장 버튼이 사용
2. **언어 전환 (한국어/English)**
   - `regions.py`에 `name_en`/`description_en` 병기, ops/guide payload에 포함
   - 프론트 i18n 딕셔너리: 지역명·설명, 도움말 오버레이, 툴팁, 설정 라벨 전환
     (콘솔 mono 크롬은 디자인상 양쪽 모두 영문 유지, Intel 리포트는 한국어)
   - 커맨드 팔레트 "Toggle language" 액션, localStorage 지속
3. **Settings 뷰** (단축키 `6`, 레일 아이콘 신설)
   - 언어 선택 버튼, 추적 자산 편집기(추가/삭제/이름/유형/설명/on-off 체크),
     저장 시 토스트 + 워치리스트/집계 즉시 갱신, API 엔드포인트 안내
4. **테스트**: `tests/test_asset_config.py` 6건 신규 (기본값 로드, 섹션 갱신
   round-trip + 타 섹션 보존, 커스텀 메타 반영, 비활성 자산 집계 제외,
   지역 영문 메타, /config 노출)

### 운영 영향
- Breaking change 없음 — `assets` 미설정 시 기존과 동일한 기본 자산 메타 사용
- `PUT /config/assets`는 `KAVEN_CONFIG`(기본 `src/kaven/config.json`)에 기록

### 검증 결과
- `ruff check .` → All checks passed / `pytest` → 64 passed (기존 실패 1건 동일)
- 브라우저 E2E: Settings 뷰 렌더링(기본 8종), EN 전환 시 워치리스트·인스펙터
  영문 표시, 자산 추가+저장 토스트, 새로고침 후 언어 유지, 콘솔 에러 0

---

## v0.0.11 — 2026-07-19

### 핵심: 내장 벡터 월드맵 — COP 지도의 외부 의존성 제거

기존 COP 지도는 CDN(unpkg Leaflet + CARTO 타일)에 의존해 차단/오프라인
환경에서는 빈 격자(OFFLINE GRID MODE)만 보였다. 이제 지도가 항상 렌더링된다.

1. **로컬 번들** (`webapp/frontend/vendor/`, `data/`)
   - Leaflet 1.9.4 (js/css) + topojson-client 3.x + Natural Earth 110m
     국경 TopoJSON(`countries-110m.json`, 108KB) 총 ~277KB를 저장소에 포함
   - 라이선스 파일 동봉 (Leaflet BSD-2, topojson-client ISC,
     Natural Earth public domain)
2. **벡터 다크 월드맵 베이스**
   - CARTO 타일 레이어 제거 → 전용 pane(z=250)에 국경 GeoJSON 렌더링
     (마커·감시구역은 overlayPane z=400으로 항상 위)
   - 다크 팔레트(#161d27 육지 / #2e3a48 국경 / #0a0e14 해양)로 Palantir 룩 유지
   - `maxBounds`로 세계 범위 고정, 범례에 "BASEMAP · NATURAL EARTH" 표기
3. **SVG 폴백 개선** (Leaflet 로드 실패라는 극단 케이스용)
   - 빈 격자 → 동일 TopoJSON으로 국경 윤곽까지 그리는 정적 지도로 개선
   - 문구를 "STATIC GRID MODE — MAP LIBRARY UNAVAILABLE"로 정정
4. **기타**
   - 인라인 SVG 파비콘 추가 (favicon.ico 404 노이즈 제거)
   - README/webapp README 지도 설명 현행화, COP 스크린샷 2종 갱신
     (`cop.png` 월드 뷰, `cop-zoom.png` 한반도 AO 줌 신규)

### 운영 영향
- 프론트엔드가 인터넷 없이 완전 동작 (백엔드 API만 있으면 됨)
- 정적 서빙 용량 +277KB (최초 1회 로드 후 브라우저 캐시)

### 검증 결과
- 브라우저 확인: 로컬 Leaflet 로드, 국가 벡터 path 177개 렌더링, 콘솔 에러 0
  (favicon 404도 제거), 월드 뷰/줌 뷰 스크린샷 캡처
- `ruff check .` / `pytest` — 백엔드 무변경 (58 passed, 기존 실패 1건 동일)

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
