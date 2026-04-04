# Kaven (Maven) - 지정학 조기경보 시스템

팔란티어 Maven Smart System 스타일의 다중 데이터 소스 실시간 수집·분석·알림 개인용 시스템.

## 🎯 목적

- **지정학 리스크 감시**: 중동, 대만 해협, 한반도 등 주요 감시 공역 모니터링
- **실시간 데이터 수집**: AIS (선박), ADS-B (항공기), 뉴스, 소셜 미디어
- **자동 분석**: 이벤트 상관관계 분석 및 유사도 감지
- **투자 신호 생성**: 지정학 리스크 기반 투자 신호 생성

## 📁 프로젝트 구조

```
kaven/
├── maven.py              # 메인 오케스트레이션 로직
├── analyzer.py           # 이벤트 상관관계 분석 엔진
├── signal_generator.py   # 투자 신호 생성기
├── collectors/           # 데이터 수집기
│   ├── ais_collector.py  # 선박 AIS 데이터 수집
│   ├── adsb_collector.py # 항공기 ADS-B 데이터 수집
│   ├── news_collector.py # 뉴스 피드 수집
│   └── social_collector.py # 소셜 미디어 수집
├── logs/                 # 수집된 데이터 로그
└── README.md             # 이 파일
```

## 🚀 빠른 시작

### 1. 의존성 설치

```bash
pip3 install aiohttp python-dotenv feedparser
```

### 2. 환경 변수 설정

`.env` 파일에 다음 변수를 설정하세요:

```bash
# OpenSky Network 인증 (선택)
OPENSKY_USERNAME=your_username
OPENSKY_PASSWORD=your_password

# 알림 설정 (선택)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. 실행

```bash
# 1 회 실행
python3 maven.py --once

# 감시 모드 (5 분 간격)
python3 maven.py --watch

# 테스트 알림 발송
python3 maven.py --test
```

## 🔍 주요 기능

### 데이터 수집기 (Collectors)

- **AIS Collector**: 선박 실시간 위치 데이터 수집
- **ADS-B Collector**: 항공기 실시간 위치 데이터 수집 (군용기 감지)
- **News Collector**: 뉴스 피드 수집 및 분석
- **Social Collector**: 소셜 미디어 모니터링

### 분석 엔진 (Analyzer)

- **이벤트 상관관계 분석**: 여러 소스의 데이터 간 연관성 분석
- **유사도 감지**: 중복 이벤트 식별 및 병합
- **지정학 리스크 평가**: 수집된 데이터 기반 리스크 점수 산출

### 신호 생성기 (Signal Generator)

- **투자 신호 생성**: 지정학 리스크 기반 매수/매도 신호 생성
- **신호 검증**: 과거 데이터 기반 신호 신뢰도 평가
- **알림 발송**: Telegram 등을 통한 실시간 알림

## 📊 감시 공역

| 공역 | 설명 | 위도 | 경도 |
|------|------|------|------|
| 중동 | 이란·이라크·걸프 지역 | 24.0-38.0 | 44.0-62.0 |
| 대만 해협 | 대만 주변 해역 | 22.0-27.0 | 117.0-122.0 |
| 한반도 | 한반도及周边 공역 | 33.0-43.0 | 124.0-132.0 |

## 🛠️ 기술 스택

- **언어**: Python 3.11+
- **비동기 처리**: asyncio, aiohttp
- **데이터 처리**: feedparser (RSS/Atom 피드)
- **환경 관리**: python-dotenv

## 📝 라이선스

이 프로젝트는 개인 학습 및 연구 목적으로 개발되었습니다.

## 🤝 기여

이슈 및 PR 을 환영합니다!
