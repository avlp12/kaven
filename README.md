# Kaven

Kaven은 AIS/ADS-B/뉴스/소셜 데이터를 수집해 지정학 이벤트를 분석하고 알림을 보내는 경량 조기경보 시스템입니다.

## 프로젝트 구조

```
kaven/
├── src/
│   └── kaven/
│       ├── kaven.py
│       ├── analyzer.py
│       ├── signal_generator.py
│       ├── collectors/
│       └── logs/
├── tests/
│   ├── test_kaven_dedup.py
│   └── test_kaven_log_replay_integration.py
├── webapp/
│   ├── backend/app.py
│   └── frontend/index.html
├── Makefile
└── pytest.ini
```

## 빠른 실행

```bash
pip install aiohttp feedparser websockets
python src/kaven/kaven.py --once
python src/kaven/kaven.py --watch --interval 5
```

## 테스트

```bash
make test
make test-kaven
```

## 웹 앱 포팅 스캐폴드

웹 앱 포팅용 최소 구조를 `webapp/`에 추가했습니다.

```bash
pip install fastapi uvicorn
uvicorn webapp.backend.app:app --reload --port 8000
python -m http.server 8080 --directory webapp/frontend
```

