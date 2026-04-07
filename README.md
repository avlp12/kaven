# Kaven

Kaven은 지정학 이벤트를 수집(AIS/ADS-B/뉴스/소셜)하고, 분석/중복제거 후 알림으로 전달하는 조기경보 시스템입니다.

## 1. 프로젝트 구성

- `src/kaven/kaven.py` : 메인 실행기 (`--once`, `--watch`)
- `src/kaven/collectors/` : 데이터 수집기
- `src/kaven/analyzer.py` : 이벤트 분석 로직
- `src/kaven/signal_generator.py` : 알림 발송 로직
- `tests/test_kaven_dedup.py` : dedup 단위 테스트
- `tests/test_kaven_log_replay_integration.py` : 로그 리플레이 통합 테스트
- `webapp/backend/app.py` : FastAPI 백엔드
- `webapp/frontend/index.html` : 대시보드(정적)

## 2. 빠른 실행

### 2.1 의존성 설치

```bash
pip install aiohttp feedparser websockets
```

### 2.2 실행

```bash
# 1회 실행
python src/kaven/kaven.py --once

# 감시 모드 (기본 5분)
python src/kaven/kaven.py --watch

# 감시 모드 (예: 10분)
python src/kaven/kaven.py --watch --interval 10
```

## 3. 테스트

```bash
# 전체 테스트
make test

# Kaven 핵심 테스트만
make test-kaven
```

## 4. 웹 앱 포팅 스캐폴드

### 4.1 백엔드 실행

```bash
pip install fastapi uvicorn
uvicorn webapp.backend.app:app --reload --port 8000
```

### 4.2 프론트 실행

```bash
python -m http.server 8080 --directory webapp/frontend
```

브라우저에서 `http://127.0.0.1:8080` 접속 후 백엔드(`http://127.0.0.1:8000`)와 연동됩니다.

## 5. 운영 참고

- `.env` 파일 경로: `src/kaven/.env`
- 대시보드 기능: 이벤트 리스트/필터/자동 폴링/SSE 실시간 업데이트
- 추가 운영 문서:
  - `docs/release-notes.md`
  - `docs/webapp-checklist.md`
  - `deploy/systemd/kaven.service`
  - `deploy/docker/docker-compose.yml`
