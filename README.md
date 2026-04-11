# Kaven

**KAVEN = Korean AI-based Vigilance for Event Navigation**

Kaven은 AIS/ADS-B/뉴스/소셜 데이터를 수집하고, LLM 분석 + dedup 후 텔레그램 알림/로그 저장까지 수행하는 지정학 조기경보 시스템입니다.

현재 버전: **0.0.01**

버전 정책:
- 모든 업데이트 시 버전을 올리고(`0.0.01`부터 시작), 릴리스 노트/알림 헤더/로그 메타데이터에 동일 버전을 표시합니다.

### 최근 업데이트 (v0.0.01)
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

### 2.1 AIS (해상)
- 파일: `src/kaven/collectors/ais_collector.py`
- 감시 지역:
  - 호르무즈 해협
  - 말라카 해협
- 미설정 시 동작:
  - `AISSTREAM_API_KEY`가 없으면 시뮬레이션 모드로 동작

### 2.2 ADS-B (항공)
- 파일: `src/kaven/collectors/adsb_collector.py`
- 감시 공역:
  - 중동(이란·이라크·걸프)
  - 대만 해협
  - 한반도
- 인증:
  - 현재 코드 기준 OpenSky는 `OPENSKY_USERNAME`/`OPENSKY_PASSWORD` BasicAuth 사용
  - 인증값 없으면 비인증 모드(rate limit 더 엄격)

### 2.3 뉴스
- 파일: `src/kaven/collectors/news_collector.py`
- 소스:
  - Reuters/AP/BBC RSS
  - 로컬 SearxNG(`SEARXNG_URL`, 기본 `http://localhost:8080`)

### 2.4 소셜
- 파일: `src/kaven/collectors/social_collector.py`
- 소스:
  - SearxNG 검색 우선
  - PinchTab 브라우저 폴백
- 주의:
  - 현재 `social_collector.py`는 `SEARXNG_URL` env 대신 내부 상수(`http://localhost:8080`)를 사용

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
