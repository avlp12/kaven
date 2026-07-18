# Kaven Web App — Ops Console

Kaven 웹 앱. v0.0.06부터 프론트엔드는 Palantir Maven 스타일의
다중 패널 **작전 콘솔(Ops Console)** 로 동작합니다.

## 구조

- `backend/app.py`: FastAPI 엔드포인트
  - `GET /health`
  - `GET /ops/summary` — 작전 콘솔용 통합 요약 (지역 + 이벤트 + 자산 + 감시구역, `?date=YYYYMMDD`)
  - `GET /runs` (이벤트 리스트 + 필터), `GET /runs/latest`, `GET /runs/files`
  - `POST /runs/once`
  - `GET /runs/stream` (SSE)
  - `GET /report`, `GET /report/{date}`, `GET /report/dates`
  - `GET /guide`, `GET /guide/{region}`
  - `GET /map/data`
  - `GET /portfolio`, `GET /portfolio/{asset}`
  - `GET /config`
- `backend/ops.py`: `/ops/summary` 집계 로직 + 지역 좌표(`REGION_COORDS`)
- `frontend/index.html`: 단일 파일 Ops Console SPA (vanilla JS + Leaflet CDN)

## 백엔드 실행

```bash
pip install fastapi uvicorn
uvicorn webapp.backend.app:app --reload --port 8000
```

## 프론트 실행

정적 파일이므로 아무 정적 서버로 열면 됩니다.

```bash
python -m http.server 8080 --directory webapp/frontend
```

브라우저에서 `http://127.0.0.1:8080` 접속.
API 주소가 다르면 `http://127.0.0.1:8080/?api=http://다른호스트:8000` 형태로 override.

## Ops Console 구성

- **COP (Common Operating Picture)** — 다크 전술 지도(Leaflet + CARTO dark)
  - AIS/ADS-B 감시구역 bounding box 오버레이
  - 지역별 severity 마커 (severity ≥ 4 펄스 링)
  - 하단 24시간 이벤트 타임라인 스트립 (UTC)
  - 오프라인/CDN 차단 시 SVG 격자 지도 자동 폴백
- **좌측 레일** — COP / Event Feed / Intel Report / Asset Impact / System 전환
- **워치리스트** — AO(감시 지역) severity 정렬 + 영향 자산
- **인스펙터(우측)** — 이벤트 상세 / 지역 도시에(7일 스파크라인 포함)
- **Event Feed** — severity/category/signal/텍스트 필터 테이블
- **Intel Report** — 일일 브리핑 마크다운 렌더링
- **Asset Impact** — 자산별 7일 severity 히트맵
- **System** — 수집 파이프라인/감시구역/피드/키워드 상태 보드
- **커맨드 팔레트** — `Ctrl+K` 또는 `/` 로 지역·이벤트·자산·뷰 통합 검색
- **상단 바** — THREATCON, UTC/KST 시계, LIVE(SSE) 토글, Run Collection

## 실시간 갱신

- LIVE 토글 ON: `GET /runs/stream` SSE로 새 run 감지 시 즉시 갱신
- LIVE OFF: 60초 주기 폴링
