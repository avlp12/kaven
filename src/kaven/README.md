# Kaven Smart System 운영 가이드

Kaven은 다중 데이터 소스(AIS/ADS-B/뉴스/소셜)를 수집하고, 지정학 이벤트를 분석해 알림으로 전달하는 개인용 조기경보 시스템입니다.

## 핵심 동작

1. **수집**: AIS, ADS-B, 뉴스, 소셜 데이터를 병렬 수집
2. **분석**: LLM(우선 Gemini, 폴백 Anthropic, 최종 규칙 기반)으로 이벤트 추출
3. **중복 제거**: 유사도/수치/엔티티/URL 기준으로 이미 보낸 이벤트 필터링
4. **알림 발송**
   - severity 1~2: 로그만
   - severity 3 이상: Kaven 전용 토픽 알림
   - severity 5: 개인 DM 추가 발송

---

## 디렉터리 구조

```
src/kaven/
├── kaven.py                 # 메인 오케스트레이터
├── analyzer.py              # LLM 분석 엔진
├── signal_generator.py      # 텔레그램 발송
├── collectors/              # 데이터 수집기
│   ├── ais_collector.py
│   ├── adsb_collector.py
│   ├── news_collector.py
│   └── social_collector.py
└── logs/                    # 실행 로그(JSONL)
```

---

## 요구사항

- Python 3.10+
- 권장 패키지

```bash
pip install aiohttp feedparser websockets
```

---

## 환경 변수

| 변수 | 설명 | 기본값 |
|---|---|---|
| `GEMINI_API_KEY` | Gemini 분석 키(우선 경로) | 없음 |
| `ANTHROPIC_API_KEY` | Anthropic 분석 키(폴백 경로) | 없음 |
| `OPENCLAW_GATEWAY_URL` | 게이트웨이 URL | `http://localhost:18789` |
| `TELEGRAM_BOT_TOKEN` | Bot API 토큰 | 없음 |
| `TELEGRAM_CHAT_ID` | 그룹 채팅 ID | `-1003868141703` |
| `TELEGRAM_TOPIC_MAVEN` | Kaven 전용 토픽 ID(레거시 변수명 유지) | `5052` |
| `TELEGRAM_USER_DM` | 긴급 DM 사용자 ID | `40130797` |
| `AISSTREAM_API_KEY` | AIS API 키(없으면 시뮬레이션 경로) | 없음 |
| `OPENSKY_USERNAME` | ADS-B 계정 | 없음 |
| `OPENSKY_PASSWORD` | ADS-B 비밀번호 | 없음 |

`.env`는 `src/kaven/.env` 경로에 두면 자동 로드됩니다.

---

## 실행 방법

### 1회 실행

```bash
python src/kaven/kaven.py --once
```

### 감시 모드(기본 5분 간격)

```bash
python src/kaven/kaven.py --watch
```

### 감시 모드(간격 지정)

```bash
python src/kaven/kaven.py --watch --interval 10
```

> 참고: 기존 테스트 알림용 `--test` 모드는 제거되었습니다.

---

## 로그와 캐시

- 실행 로그: `src/kaven/logs/maven_YYYYMMDD.jsonl`
- 중복 전송 캐시: `src/kaven/logs/sent_cache.json`

캐시는 날짜 단위로 리셋되며, 동일 이벤트는 유사도/URL/수치 기반으로 병합됩니다.

---

## 개발자 검증

프로젝트 루트(`/workspace/kaven`)에서 실행:

```bash
make test
make test-kaven
```

- `make test`: 전체 테스트
- `make test-kaven`: Kaven 관련 테스트만 실행
