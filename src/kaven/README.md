# Kaven Runtime (src/kaven)

이 문서는 `src/kaven` 런타임 모듈 전용 설명입니다.

## 엔트리포인트

- `kaven.py` : 수집 → 분석 → dedup → 발송 오케스트레이션
- `collectors/` : AIS/ADS-B/뉴스/소셜 수집기
- `analyzer.py` : 이벤트 분석
- `signal_generator.py` : 알림 발송

## 실행

```bash
python src/kaven/kaven.py --once
python src/kaven/kaven.py --watch --interval 5
```

## 로그

- 실행 로그: `src/kaven/logs/maven_YYYYMMDD.jsonl`
- dedup 캐시: `src/kaven/logs/sent_cache.json`

## 주의

- `.env`는 `src/kaven/.env`에서 로드됩니다.
- 테스트 및 웹앱 실행 방법은 루트 `README.md`를 참고하세요.
