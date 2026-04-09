# Kaven Telegram 연동 FAQ

Kaven 알림(지정학 경보)을 텔레그램으로 받기 위한 설치/연동 과정과 자주 묻는 질문을 정리했습니다.

## 1) 텔레그램 봇은 어떻게 만드나요?

1. 텔레그램에서 `@BotFather` 대화 시작
2. `/newbot` 입력
3. 봇 이름/아이디를 순서대로 입력
4. 발급된 토큰을 복사
   - 예: `123456789:AA...`

`.env`에 아래처럼 넣습니다.

```env
TELEGRAM_BOT_TOKEN=여기에_발급받은_토큰
```

---

## 2) 봇을 그룹/채널에 어떻게 연결하나요?

1. 알림받을 그룹(또는 포럼형 슈퍼그룹)에 봇 초대
2. 봇에게 **메시지 전송 권한** 부여
3. (권장) 테스트 메시지를 그룹에 1번 보내 봇 접근 가능 상태 확인

---

## 3) `TELEGRAM_CHAT_ID`는 어떻게 구하나요?

방법 A (권장):
- 봇을 그룹에 초대한 뒤, 봇 API `getUpdates` 응답에서 `chat.id` 확인

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
```

- 일반적으로 그룹/슈퍼그룹 ID는 음수(`-100...`) 형태입니다.

`.env` 예시:

```env
TELEGRAM_CHAT_ID=-1001234567890
```

---

## 4) 토픽(스레드)으로 보내려면?

Kaven은 `TELEGRAM_TOPIC_MAVEN` 값을 사용합니다.

```env
TELEGRAM_TOPIC_MAVEN=5052
```

토픽 ID(= `message_thread_id`)는 다음 방식으로 확인할 수 있습니다.
- 해당 토픽에서 메시지 1건 작성
- `getUpdates` 결과 JSON에서 `message_thread_id` 확인

---

## 5) 꼭 Bot API 토큰이 있어야 하나요?

아니요. 아래 2가지 중 하나면 됩니다.

1. `TELEGRAM_BOT_TOKEN` 기반 Telegram Bot API 직접 발송
2. `OPENCLAW_GATEWAY_URL` 기반 게이트웨이 발송(폴백)

둘 다 안 되면 Kaven 로그에 `No telegram delivery method available`가 출력됩니다.

---

## 6) DM(개인 긴급 알림)은 어떻게 쓰나요?

긴급(Severity 5+) 알림을 개인 DM으로 받으려면:

```env
TELEGRAM_USER_DM=사용자ID
```

주의:
- 봇과 해당 사용자 간에 대화 시작 이력이 있어야 DM 전송이 가능한 경우가 많습니다.

---

## 7) 자주 나는 오류와 해결법

### Q. `Telegram Bot API 실패: 400`가 떠요.
A.
- `TELEGRAM_CHAT_ID` 오타/형식 오류 가능성 큼
- 토픽 사용 시 `TELEGRAM_TOPIC_MAVEN` 값 확인

### Q. `403 Forbidden`이 떠요.
A.
- 봇이 그룹/채널에 없거나 메시지 권한이 없음
- 채널 권한(관리자 권한 포함) 확인

### Q. `No telegram delivery method available`가 떠요.
A.
- `TELEGRAM_BOT_TOKEN` 미설정 + `OPENCLAW_GATEWAY_URL` 연결 실패 상태

### Q. 메시지는 가는데 토픽으로 안 가요.
A.
- 포럼형 슈퍼그룹인지 확인
- `message_thread_id`(= `TELEGRAM_TOPIC_MAVEN`) 재확인

---

## 8) 최소 동작 환경변수 예시

```env
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_TOPIC_MAVEN=5052
# 선택
TELEGRAM_USER_DM=40130797
OPENCLAW_GATEWAY_URL=http://localhost:18789
```

