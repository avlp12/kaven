# Kaven

**KAVEN = Korean AI-based Vigilance for Event Navigation**

Kaven은 AIS/ADS-B/뉴스/소셜 데이터를 수집하고, LLM 분석 + dedup 후 텔레그램 알림/로그 저장까지 수행하는 지정학 조기경보 시스템입니다.

현재 버전: **0.0.08**

버전 정책:
- 모든 업데이트 시 버전을 올리고(`0.0.01`부터 시작), 릴리스 노트/알림 헤더/로그 메타데이터에 동일 버전을 표시합니다.

### 최근 업데이트 (v0.0.08)
- **Ops Console 운영 능률(UX efficiency) 개선** — 프론트엔드 리뷰 후 조정.
  - **전역 키보드 단축키**: `1`–`5` 뷰 전환, `J`/`K` 이벤트 순회(피드 정렬 순서 따름), `F` 피드+필터 포커스, `R` 수집 실행, `L` LIVE 토글, `Esc` 선택 해제, `?` 단축키 도움말 오버레이.
  - **상태 지속성(localStorage)**: 마지막 뷰, 피드 필터, 정렬, LIVE 상태, 조용한 AO 표시 여부를 새로고침 후에도 복원.
  - **데이터 신선도 표시**: 상단바 `SYNC n초 AGO` 실시간 표시, 90초 초과 시 경고색.
  - **워치리스트 노이즈 감소**: S0·이벤트 0 지역은 접고 `+n QUIET` 토글로 펼침. 자산 클릭 시 Feed로 이동해 해당 자산 필터 자동 적용.
  - **피드 정렬**: Time/Sev 헤더 클릭 정렬(방향 토글, ▾/▴ 표시).
  - **인스펙터**: `‹`/`›` 이전·다음 이벤트 탐색, `⧉ JSON` 이벤트 복사 버튼.
  - **커맨드 팔레트 액션 추가**: "Copy ops briefing (LLM context)" — `/agent/context` 브리핑을 클립보드로 복사.

### 이전 업데이트 (v0.0.07)
- **AI 에이전트 연동 계층 신설** — 에이전트가 Kaven을 도구로 사용할 수 있게 됨.
  - **MCP 서버** (`src/kaven/mcp_server.py`): 외부 SDK 의존성 없는 stdio MCP 서버. `kaven_ops_summary`, `kaven_events`, `kaven_agent_context`, `kaven_region`, `kaven_daily_report`, `kaven_portfolio`, `kaven_config`, `kaven_run_collection` 8개 도구 제공. 등록: `claude mcp add kaven -- python -m src.kaven.mcp_server`
  - **REST `/agent/*`**: `GET /agent/manifest`(엔드포인트/도구/스키마 어휘 카탈로그), `GET /agent/context`(LLM 프롬프트 주입용 압축 브리핑), `GET /agent/events`(평탄화 이벤트 쿼리 + 필터)
- **전반 리팩토링 — 코어/HTTP 계층 분리**
  - 중복 로직 단일화: `src/kaven/log_store.py`(JSONL 로그 액세스), `src/kaven/regions.py`(지역 메타), `src/kaven/ops_summary.py`, `src/kaven/aggregates.py`(가이드/지도/포트폴리오 집계), `src/kaven/agent_service.py`
  - `webapp/backend/app.py`(436줄)를 도메인별 라우터(`webapp/backend/routers/`)로 분리 — app.py는 앱 조립만 담당
  - `KAVEN_LOG_DIR` 환경변수로 로그 디렉터리 override 가능
- **버그 수정**: `/report/dates`가 `/report/{date}`에 먼저 매칭되어 400을 반환하던 라우트 순서 버그 수정 (Intel 뷰 날짜 목록 정상화)
- 테스트: log_store 7건 + agent_service 6건 + mcp_server 7건 신규 (총 54 passed)

### 이전 업데이트 (v0.0.06)
- **Palantir 스타일 작전 콘솔(Ops Console)로 웹 UI 전면 개편** — 탭 기반 SPA를 Maven Smart System 류의 다중 패널 인텔리전스 콘솔로 재설계.
  - **COP(Common Operating Picture)**: 다크 전술 지도(Leaflet + CARTO dark) 위에 AIS/ADS-B 감시구역 박스, 지역별 severity 마커(고심각도 펄스 링), 24시간 이벤트 타임라인 스트립. 오프라인 시 SVG 격자 지도로 자동 폴백.
  - **3-패널 워크스페이스**: 좌측 아이콘 레일(COP/Feed/Intel/Assets/System) + AO 워치리스트 + 우측 인스펙터(이벤트 상세·지역 도시에·7일 스파크라인).
  - **커맨드 팔레트**(`Ctrl+K` 또는 `/`): 지역·이벤트·자산·뷰 통합 검색/이동.
  - 상단 바: THREATCON 레벨, UTC/KST 실시간 시계, LIVE(SSE) 토글, Run Collection 버튼.
- `GET /ops/summary` API 신규 (`webapp/backend/ops.py`) — 지역 상태 + 전체 이벤트(좌표·ID 포함) + 자산 영향 + 감시구역을 단일 payload로 반환. `?date=YYYYMMDD` 지원.
- 지역 좌표(`REGION_COORDS`)를 `webapp/backend/ops.py`로 이동해 guide/map/ops 엔드포인트가 공유.
- 테스트: `tests/test_ops_summary.py` 7건 신규.

### 이전 업데이트 (v0.0.04)
- **감시 구역/피드/키워드 설정 파일화** — 기존에 코드에 하드코딩되어 있던 AIS·ADS-B 감시 구역, 뉴스 RSS/키워드, 소셜 검색어를 전부 `src/kaven/config.json`(선택) 로 외부화했습니다. 각 항목에 `enabled` 플래그를 두어 **선택적 활성화/비활성화** 가능.
- `src/kaven/config_loader.py` 신규 모듈: 설정 파일 없으면 내장 기본값 fallback. `KAVEN_CONFIG` 환경변수로 경로 override.
- `src/kaven/config.example.json` 샘플 파일 제공 (바브엘만데브, 동유럽 공역, 연합뉴스 등 `enabled:false` 예시 포함).
- `/config` API 엔드포인트 신규: 현재 로드된 설정(enabled/disabled 수 포함)을 JSON으로 조회.
- 4개 collector 전부 리팩터링 — 런타임에 설정을 읽어 활성 항목만 수집.
- **Codex 리뷰 수정사항 반영** — ruff 11 errors → 0, `pyproject.toml` (ruff/mypy 설정), `requirements.txt`/`requirements-dev.txt` 추가, social_collector `SEARXNG_URL` 환경변수화.
- 테스트: `tests/test_config_loader.py` 8건 신규 (설정 로드/필터/비활성/오류복원).

### 이전 업데이트 (v0.0.03)
- **일일 분석 리포트 자동 생성** (`/report`) — JSONL 로그에서 지역별/카테고리별/자산별 집계 + 마크다운 브리핑을 자동 생성. LLM 없이 규칙 기반으로 동작하므로 API 키 불필요. `GET /report`, `GET /report/{YYYYMMDD}`, `GET /report/dates` 엔드포인트 추가.
- **인터랙티브 분쟁 지도** (`/map`) — globe.gl 3D 지구본에 실시간 이벤트 데이터를 severity별 색상 마커로 표시. 기존 하드코딩 시각화를 `GET /map/data` API 기반으로 교체. 클릭 줌, 자동 회전 지원.
- **지역별 분쟁 현황 가이드** (`/guide`) — 9개 감시구역(호르무즈, 대만, 한반도 등)의 현재 severity + 설명 + 7일 히스토리 차트. `GET /guide`, `GET /guide/{region}?days=7` 엔드포인트 추가.
- **프론트엔드 전면 리뉴얼** — 단일 테이블 → 탭 기반 다크 테마 SPA (Dashboard / Report / Map / Guide). Severity 뱃지, 통계 카드, 반응형 레이아웃.
- `report_generator.py` 모듈 신규 추가 + 테스트 6건 (`tests/test_report_generator.py`).

### 이전 업데이트 (v0.0.02)
- 이슈 #7 정책 반영: Convex 원격 업로드를 `CONVEX_SITE_URL` 기반 opt-in으로 전환.
- 하드코딩 엔드포인트 제거, `CONVEX_EVENT_PATH` 환경변수 지원.
- 정책 회귀 테스트 `tests/test_kaven_convex_policy.py` 9건 추가.
- `.gitignore` 신규 추가.

### 이전 업데이트 (v0.0.01)
- 사용자 알림 문구의 `Maven` 표기를 `Kaven`으로 통일했습니다.
- 실행 로그 파일명을 `kaven_YYYYMMDD.jsonl`로 전환했고, 구버전 `maven_*.jsonl`은 읽기 호환을 유지합니다.
- 텔레그램 경보 헤더/긴급 경보에 버전(`v0.0.01`)이 표시됩니다.
- `/health` 응답과 런타임 로그 메타데이터에 버전 필드를 포함합니다.

---

## 1) 시스템 개요

### 파이프라인
1. **수집기(collectors)**: AIS, ADS-B, 뉴스, 소셜 데이터 수집
2. **분석기(analyzer)**: OpenAI 호환(로컬 포함) → Gemini → Anthropic → 규칙기반 폴백 순으로 이벤트 분석
3. **중복 제거(kaven dedup)**: 텍스트/수치/출처 URL 기반 유사 이벤트 병합
4. **알림(signal_generator)**: Severity 기준 텔레그램 발송
5. **저장**: 로컬 JSONL 로그 + Convex 업로드 시도(실패해도 로컬 유지)

### 주요 디렉터리
- `src/kaven/kaven.py`: 메인 실행기 (`--once`, `--watch`)
- `src/kaven/collectors/`: 데이터 수집기
- `src/kaven/analyzer.py`: LLM 분석 엔진
- `src/kaven/signal_generator.py`: 알림 발송
- `webapp/backend/app.py`: FastAPI API
- `webapp/frontend/index.html`: 정적 대시보드
- `tests/`: dedup/로그 리플레이 테스트

---

## 2) 데이터 수집기 & 감시 구역

> **v0.0.04부터**: 감시 구역, RSS 피드, 키워드는 모두 설정 파일로 관리됩니다.
> 기본값은 코드에 내장되어 있어 설정 파일이 없어도 바로 동작합니다.
> 커스터마이즈하려면 `src/kaven/config.example.json`을 `src/kaven/config.json`으로 복사해서 편집하세요. 자세한 내용은 **§13 설정(Configuration)** 참조.

### 2.1 AIS (해상)
- 파일: `src/kaven/collectors/ais_collector.py`
- 설정 키: `ais_zones`
- 기본 감시 지역:
  - 호르무즈 해협
  - 말라카 해협
- 미설정 시 동작:
  - `AISSTREAM_API_KEY`가 없으면 시뮬레이션 모드로 동작 (활성화된 zone만)

### 2.2 ADS-B (항공)
- 파일: `src/kaven/collectors/adsb_collector.py`
- 설정 키: `adsb_zones`
- 기본 감시 공역:
  - 중동(이란·이라크·걸프)
  - 대만 해협
  - 한반도
- 인증:
  - OpenSky는 `OPENSKY_USERNAME`/`OPENSKY_PASSWORD` BasicAuth 사용
  - 인증값 없으면 비인증 모드(rate limit 더 엄격)

### 2.3 뉴스
- 파일: `src/kaven/collectors/news_collector.py`
- 설정 키: `news_feeds`, `news_keywords`
- 기본 소스:
  - Reuters/AP/BBC RSS
  - 로컬 SearxNG(`SEARXNG_URL`, 기본 `http://localhost:8080`)

### 2.4 소셜
- 파일: `src/kaven/collectors/social_collector.py`
- 설정 키: `social_keywords`
- 소스:
  - SearxNG 검색 우선 (`SEARXNG_URL`)
  - PinchTab 브라우저 폴백 (`PINCHTAB_URL`, 기본 `http://localhost:9867`)

---

## 3) 분석 엔진

- 파일: `src/kaven/analyzer.py`
- 출력 스키마 핵심 필드:
  - `event`, `severity(1-5)`, `category`, `signal`, `confidence`, `affected_assets`, `source_url`, `event_time` 등
- 분석 경로 우선순위:
  1. **OpenAI 호환 API** (`OPENAI_BASE_URL` 설정 시; 로컬 LLM 가능)
  2. Gemini API
  3. Anthropic API
  4. 규칙 기반 `_fallback_analysis`

---

## 4) 기술 스택

- Python 3.11+
- `aiohttp`, `feedparser`, `websockets`
- FastAPI + Uvicorn (웹 API)
- Pytest (테스트)
- Docker / docker-compose (배포 스캐폴드)
- systemd 서비스 파일 제공 (`deploy/systemd/kaven.service`)

---

## 5) 빠른 시작

### 5.1 의존성 설치
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install aiohttp feedparser websockets fastapi uvicorn pytest
```

### 5.2 `.env` 준비
Kaven은 `src/kaven/.env`를 자동 로드합니다.

```bash
cat > src/kaven/.env <<'ENV'
# ===== 수집 =====
OPENSKY_USERNAME=
OPENSKY_PASSWORD=
AISSTREAM_API_KEY=
SEARXNG_URL=http://localhost:8080

# ===== 분석 =====
OPENAI_BASE_URL=
OPENAI_API_KEY=
OPENAI_MODEL=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=

# ===== 알림 =====
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_TOPIC_MAVEN=5052
TELEGRAM_USER_DM=

# ===== 원격 백업 (opt-in, 이슈 #7 정책) =====
# 기본은 로컬 로그만 저장하며 외부 전송은 완전 비활성화됩니다.
# 필요한 경우에만 CONVEX_SITE_URL을 명시적으로 설정해 opt-in 하세요.
# CONVEX_EVENT_PATH는 경로 override (기본 /addKavenRun).
CONVEX_SITE_URL=
CONVEX_EVENT_PATH=/addKavenRun

# ===== 기타 =====
OPENCLAW_GATEWAY_URL=http://localhost:18789
ENV
```

> 보안 주의: `.env`는 절대 Git에 커밋하지 마세요.
> 운영 주의 (이슈 #7 정책): `CONVEX_SITE_URL`을 명시적으로 설정하지 않으면 이벤트 payload는 어떤 외부 엔드포인트로도 전송되지 않습니다. 하드코딩된 Convex endpoint는 제거되었으며, 원격 백업이 필요한 경우에만 opt-in 하세요.

### 5.3 실행
```bash
# 1회 실행
python src/kaven/kaven.py --once

# 감시 모드 (기본 5분)
python src/kaven/kaven.py --watch

# 감시 모드 (예: 10분)
python src/kaven/kaven.py --watch --interval 10
```

---

## 6) 인프라 실행

### 6.1 로컬 SearxNG (예시)
```bash
docker run --rm -d --name searxng -p 8080:8080 searxng/searxng
curl -s "http://localhost:8080/search?q=Hormuz&format=json" | head
```

> macOS + Colima 사용 시 먼저 `colima start` 후 Docker 명령 실행.

### 6.2 docker-compose
```bash
cd deploy/docker
docker compose up -d
docker compose ps
```

---

## 7) 웹앱

### 백엔드
```bash
uvicorn webapp.backend.app:app --reload --port 8000
```

### 프론트
```bash
python -m http.server 8080 --directory webapp/frontend
```

접속: `http://127.0.0.1:8080`

---

## 8) 운영/트러블슈팅

### 로그/캐시
- 실행 로그: `src/kaven/logs/kaven_YYYYMMDD.jsonl` (구버전 `maven_*.jsonl`도 읽기 호환)
- dedup 캐시: `src/kaven/logs/sent_cache.json`

### 자주 발생하는 문제
- `CHAT_ID`가 아니라 `TELEGRAM_CHAT_ID`를 써야 함
- `.env`는 루트가 아니라 `src/kaven/.env`에 있어야 자동 로드됨
- SearxNG 미구동 시 뉴스/소셜 수집 저하
- `CONVEX_SITE_URL 미설정 — 외부 전송 스킵` 로그: 정상 동작입니다. 기본 정책(이슈 #7)상 외부 전송은 opt-in이며, 로컬 로그는 이미 저장되어 있습니다. 원격 백업이 필요하면 `CONVEX_SITE_URL`을 설정하세요.
- `Convex 저장 실패 (로컬 로그는 유지)`가 떠도 로컬 로그는 정상 저장됨 (원격 실패는 예외로 전파되지 않음)

### 텔레그램 FAQ
- 텔레그램 봇 생성, `TELEGRAM_CHAT_ID`/토픽 ID 확인, DM 설정, 오류 해결은 아래 문서를 참고하세요.
- 문서: `docs/telegram-faq.md`

---

## 9) 테스트

```bash
# 전체 테스트
make test

# Kaven 핵심 테스트
make test-kaven

# 직접 실행
pytest -q
```

---

## 10) 라이선스

이 프로젝트는 **MIT License**를 사용합니다.

- 개인/상업적 사용, 수정, 재배포를 자유롭게 허용합니다.
- 단, 배포 시 저작권 고지와 라이선스 본문(`LICENSE`)을 포함해야 합니다.

---

## 11) 기여(Contributing)

1. 이슈 또는 변경 목적을 먼저 정리합니다.
2. 기능 브랜치를 생성합니다.
3. 코드 변경 후 `pytest -q`를 통과시킵니다.
4. 문서(README/운영 가이드)도 함께 업데이트합니다.
5. PR에 변경 이유/테스트 결과/운영 영향도를 명확히 작성합니다.

---

## 12) 추가 문서

- `src/kaven/README.md`
- `webapp/README.md`
- `docs/release-notes.md`
- `docs/webapp-checklist.md`
- `docs/telegram-faq.md`
- `deploy/systemd/kaven.service`
- `deploy/docker/docker-compose.yml`

---

## 13) 설정 (Configuration)

v0.0.04부터 감시 구역, RSS 피드, 뉴스·소셜 키워드를 JSON 설정 파일로 관리합니다.

### 13.1 설정 파일 위치

탐색 순서:
1. `KAVEN_CONFIG` 환경변수가 가리키는 경로
2. `src/kaven/config.json` (기본)
3. 파일 없으면 내장 기본값 사용 (기존 동작과 완전 호환)

### 13.2 설정 파일 생성

```bash
cp src/kaven/config.example.json src/kaven/config.json
# 편집 후 재시작
python src/kaven/kaven.py --once
```

### 13.3 스키마

```json
{
  "ais_zones": [
    {"id": "hormuz", "name": "호르무즈 해협", "enabled": true,
     "lat_min": 25.5, "lat_max": 27.0, "lon_min": 56.0, "lon_max": 57.5, "baseline_ships": 50},
    {"id": "malacca", "name": "말라카 해협", "enabled": false, ...}
  ],
  "adsb_zones": [
    {"id": "middle_east", "name": "중동", "enabled": true,
     "lat_min": 24.0, "lat_max": 38.0, "lon_min": 44.0, "lon_max": 62.0}
  ],
  "news_feeds": [
    {"id": "reuters_world", "name": "Reuters World", "enabled": true,
     "url": "https://feeds.reuters.com/Reuters/worldNews"}
  ],
  "news_keywords": [
    {"id": "iran_military", "query": "Iran military", "enabled": true}
  ],
  "social_keywords": [
    {"id": "iran_hormuz", "query": "Iran Hormuz", "enabled": true}
  ]
}
```

### 13.4 각 항목의 `enabled` 플래그

- `true` (기본): 해당 구역/피드/키워드 활성화
- `false`: 수집에서 제외하지만 설정 파일에는 유지 (나중에 다시 활성화 가능)
- 플래그 미지정 시 `true`로 간주

### 13.5 현재 설정 확인

```bash
# 웹 API로 현재 활성/비활성 항목 조회
curl http://127.0.0.1:8000/config
```

### 13.7 로그 디렉터리 override

- `KAVEN_LOG_DIR` 환경변수로 JSONL 로그 디렉터리를 변경할 수 있습니다 (기본 `src/kaven/logs`).

### 13.6 부분 override

설정 파일에 특정 섹션만 포함해도 됩니다. 예를 들어 AIS 구역만 커스터마이즈하고 싶으면:

```json
{
  "ais_zones": [
    {"id": "bab_el_mandeb", "name": "바브엘만데브", "enabled": true,
     "lat_min": 12.0, "lat_max": 14.0, "lon_min": 42.5, "lon_max": 44.0}
  ]
}
```

→ `ais_zones`만 치환되고 나머지(`adsb_zones`, `news_feeds`, 등)는 내장 기본값 사용.

---

## 14) AI 에이전트 연동 (Agent Integration)

v0.0.07부터 AI 에이전트가 Kaven을 도구로 사용할 수 있습니다.

### 14.1 MCP 서버 (권장)

외부 SDK 의존성 없는 stdio MCP 서버를 내장합니다.

```bash
# Claude Code에 등록 (저장소 루트에서)
claude mcp add kaven -- python -m src.kaven.mcp_server
```

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "kaven": {
      "command": "python",
      "args": ["-m", "src.kaven.mcp_server"],
      "cwd": "/path/to/kaven"
    }
  }
}
```

제공 도구 (8개):

| 도구 | 설명 |
|---|---|
| `kaven_ops_summary` | 통합 상황 요약 (위협 수준·지역·이벤트·자산·감시구역) |
| `kaven_events` | 평탄화 이벤트 쿼리 (severity/지역/카테고리/신호/키워드 필터) |
| `kaven_agent_context` | LLM 프롬프트 주입용 압축 마크다운 브리핑 |
| `kaven_region` | 지역 상세 + 최근 N일 severity 히스토리 |
| `kaven_daily_report` | 규칙 기반 일일 브리핑 (마크다운) |
| `kaven_portfolio` | 자산별 투자 영향 집계 |
| `kaven_config` | 수집 설정 조회 |
| `kaven_run_collection` | 수집 파이프라인 1회 즉시 실행 |

### 14.2 REST API

웹 백엔드 구동 중이면 HTTP로도 동일 기능을 사용할 수 있습니다.

```bash
# 에이전트 디스커버리 — 엔드포인트/도구/스키마 어휘 카탈로그
curl http://127.0.0.1:8000/agent/manifest

# LLM 컨텍스트 주입용 압축 브리핑
curl "http://127.0.0.1:8000/agent/context?severity_min=3&max_events=10"

# 평탄화 이벤트 쿼리
curl "http://127.0.0.1:8000/agent/events?region=korea&severity_min=4"
```

- OpenAPI 스키마: `GET /openapi.json` (Swagger UI: `/docs`)
- 이벤트 스키마 어휘(지역 코드, 카테고리, 신호, severity 의미)는 `/agent/manifest`의 `vocabulary` 필드 참조.
