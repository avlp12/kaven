# Kaven Release Notes (Template)

## 버전
- Version: v0.1.0
- Date: YYYY-MM-DD

## 주요 변경사항
1. Maven → Kaven 리브랜딩 및 경로 정리
2. dedup 로직 강화 (수치 토큰/소스 URL/동일 이벤트 판정)
3. 웹앱 스캐폴드 추가 (API + 대시보드)
4. 테스트/개발 편의성 개선 (`Makefile`, `pytest.ini`)

## 운영 영향
- 배포 시 `.env` 경로는 `src/kaven/.env`
- 웹 백엔드 기본 포트: `8000`
- 정적 프론트 기본 포트: `8080`

## 검증 결과
- `make test`
- `make test-kaven`
- (선택) `python -m py_compile webapp/backend/app.py`

## 롤백
- 이전 태그/커밋으로 롤백
- 서비스 재시작
