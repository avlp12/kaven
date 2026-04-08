# Kaven

**KAVEN = Korean AI-based Vigilance for Event Navigation**

Kaven은 지정학 이벤트를 수집(AIS/ADS-B/뉴스/소셜)하고, 분석/중복 제거 후 텔레그램 알림으로 전달하는 조기경보 시스템입니다.

## 1. 프로젝트 구성

- `src/kaven/kaven.py` : 메인 실행기 (`--once`, `--watch`)
- `src/kaven/collectors/` : 데이터 수집기 (AIS/ADS-B/뉴스/소셜)
- `src/kaven/analyzer.py` : 이벤트 분석 로직 (Gemini 우선, Anthropic 폴백)
- `src/kaven/signal_generator.py` : 텔레그램/게이트웨이 알림 발송
- `tests/test_kaven_dedup.py` : dedup 단위 테스트
- `tests/test_kaven_log_replay_integration.py` : 로그 리플레이 통합 테스트
- `webapp/backend/app.py` : FastAPI 백엔드
- `webapp/frontend/index.html` : 대시보드(정적)

---

## 2. 빠른 실행

### 2.1 의존성 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install aiohttp feedparser websockets fastapi uvicorn pytest
```

### 2.2 `.env` 파일 준비 (필수)

Kaven은 실행 시 `src/kaven/.env`를 자동 로드합니다.

```bash
cat > src/kaven/.env <<'ENV'
# ===== 데이터 수집 =====
OPENSKY_USERNAME=
OPENSKY_PASSWORD=
AISSTREAM_API_KEY=
SEARXNG_URL=http://localhost:8080

# ===== 분석 엔진 (하나 이상 권장) =====
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

# ===== 폴백 게이트웨이 (선택) =====
OPENCLAW_GATEWAY_URL=http://localhost:18789
ENV
```

> 보안 주의: `.env`에는 민감정보가 포함되므로 Git에 커밋하지 마세요.

### 2.3 실행

```bash
# 1회 실행
python src/kaven/kaven.py --once

# 감시 모드 (기본 5분)
python src/kaven/kaven.py --watch

# 감시 모드 (예: 10분)
python src/kaven/kaven.py --watch --interval 10
```

---

## 3. 실사용 필수 설정 체크리스트 (중요)

아래 항목 중 누락되면 **시뮬레이션/폴백 모드**로 동작하거나 일부 기능이 실패할 수 있습니다.

### 3.1 데이터 수집

- `AISSTREAM_API_KEY`
  - 미설정 시 AIS는 실데이터 대신 **시뮬레이션 데이터**를 사용합니다.
- `OPENSKY_USERNAME` / `OPENSKY_PASSWORD`
  - 없으면 ADS-B는 비인증 모드로 동작하며 rate limit이 더 엄격합니다.
- `SEARXNG_URL`
  - 기본값은 `http://localhost:8080`.
  - SearxNG가 미구동이면 뉴스/소셜 검색이 크게 제한됩니다.
  - `social_collector.py`는 현재 `SEARXNG_URL`이 아닌 내부 상수(`http://localhost:8080`)를 사용하므로, 주소를 바꿨다면 해당 파일도 함께 수정해야 합니다.
- OpenSky 인증 방식
  - **현재 코드 기준** OpenSky는 OAuth2가 아니라 `OPENSKY_USERNAME`/`OPENSKY_PASSWORD` BasicAuth 흐름을 사용합니다.
  - OAuth2로 운용 중이라면 collector 코드와 README를 함께 업데이트해 혼선을 방지하세요.

### 3.2 분석 엔진

- 로컬 LLM(OpenAI 호환 API) 사용 시:
  - `OPENAI_BASE_URL` 예: `http://localhost:11434`(ollama+proxy), `http://localhost:8001`
  - `OPENAI_MODEL` 예: `qwen2.5:14b`, `llama-3.1-8b-instruct`
  - `OPENAI_API_KEY`는 서버가 요구할 때만 설정 (로컬 서버는 빈 값 허용 가능)
- `GEMINI_API_KEY` 또는 `ANTHROPIC_API_KEY` 중 최소 1개 권장.
- 분석 시도 순서: **OpenAI 호환 API → Gemini → Anthropic → 규칙 기반 폴백**.
- 모든 경로가 실패하면 규칙 기반 `_fallback_analysis`로 동작합니다.

### 3.3 알림(텔레그램/OpenClaw)

- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` 설정 시 Telegram Bot API 직접 발송.
- `TELEGRAM_BOT_TOKEN`이 없으면 `OPENCLAW_GATEWAY_URL` 폴백 발송을 시도.
- 긴급 DM 사용 시 `TELEGRAM_USER_DM` 필요.
- 토픽 사용 시 `TELEGRAM_TOPIC_MAVEN` 값을 채널/포럼 토픽에 맞게 설정.
- Bot Token이 없고 `OPENCLAW_GATEWAY_URL`도 불가하면 알림 발송은 실패합니다.

### 3.4 저장소(Convex) 동작

- Kaven은 실행 종료 시 이벤트가 있으면 Convex endpoint(`https://exciting-cod-257.convex.site/addMavenRun`)로 업로드를 시도합니다.
- 업로드 실패해도 로컬 로그(`src/kaven/logs/maven_YYYYMMDD.jsonl`)는 유지됩니다.
- 즉, 웹 대시보드 연동이 필요하면 Convex 접근 가능 여부를 별도로 점검해야 합니다.

### 3.5 자주 발생하는 설정 실수

- 변수명 실수: `CHAT_ID`가 아니라 **`TELEGRAM_CHAT_ID`**를 사용해야 합니다.
- `.env` 경로 실수: 루트가 아니라 **`src/kaven/.env`**에 있어야 자동 로드됩니다.
- 로컬 SearxNG 미구동: `localhost:8080` 연결 실패 시 뉴스/소셜 수집 로그에 경고가 발생합니다.
- 로그 경로 혼동: 현재 저장 기본 경로는 `src/kaven/logs/`입니다.

---

## 4. 현재 동작 모드 확인 방법

실행 로그에서 아래 키워드를 확인하세요.

- `AISSTREAM_API_KEY 미설정 — 시뮬레이션 모드로 동작`
- `OpenSky 인증 정보 미설정 — 비인증 모드`
- `SearxNG ... 실패` / `HTTP 403` / 연결 오류
- `모든 분석 경로 실패` (AI 키 누락/실패)
- `No telegram delivery method available` (텔레그램 + 게이트웨이 모두 실패)
- `Convex 저장 실패 (로컬 로그는 유지)` (클라우드 업로드 실패)

---

## 5. 인프라/검색엔진 실행 (실사용 권장)

### 5.1 로컬 SearxNG (Docker)

`news_collector.py`와 `social_collector.py`가 `http://localhost:8080`를 기대합니다.

```bash
# 예시: 로컬에 searxng 컨테이너를 8080으로 노출
docker run --rm -d --name searxng -p 8080:8080 searxng/searxng
curl -s "http://localhost:8080/search?q=Hormuz&format=json" | head
```

> macOS에서 Docker Desktop 대신 Colima를 쓴다면 먼저 `colima start` 후 위 명령을 실행하세요.

### 5.2 docker-compose 기반 실행

```bash
cd deploy/docker
docker compose up -d
docker compose ps
```

---

## 6. 웹 앱 포팅 스캐폴드

### 6.1 백엔드 실행

```bash
uvicorn webapp.backend.app:app --reload --port 8000
```

### 6.2 프론트 실행

```bash
python -m http.server 8080 --directory webapp/frontend
```

브라우저에서 `http://127.0.0.1:8080` 접속 후 백엔드(`http://127.0.0.1:8000`)와 연동됩니다.

---

## 7. 테스트

```bash
# 전체 테스트
make test

# Kaven 핵심 테스트만
make test-kaven
```

---

## 8. 운영 참고

- `.env` 파일 경로: `src/kaven/.env`
- 실행 로그: `src/kaven/logs/maven_YYYYMMDD.jsonl`
- dedup 캐시: `src/kaven/logs/sent_cache.json`
- 대시보드 기능: 이벤트 리스트/필터/자동 폴링/SSE 실시간 업데이트
- 추가 운영 문서:
  - `docs/release-notes.md`
  - `docs/webapp-checklist.md`
  - `deploy/systemd/kaven.service`
  - `deploy/docker/docker-compose.yml`
