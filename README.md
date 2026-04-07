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
