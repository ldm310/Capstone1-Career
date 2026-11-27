# 선택 이메일 인증과 실제 발송 설정

이메일 인증은 로그인과 회원가입의 필수 조건이 아니다. `/verify-email`에서 로그인한 회원이 자기 이메일에만 인증 메일을 요청한다. 메일의 링크를 열고 버튼을 눌러 확인한다. 토큰은 30분 일회용이며 서버에는 해시만 저장한다. 이메일이 바뀌면 기존 인증은 적용되지 않는다. 현재 인증 기록은 기존 로컬 SQLite의 `email_verifications`에 저장하며 RDS의 가입 필수 여부는 변경하지 않는다.

## Gmail 발송 설정

발송용 Gmail 계정에서 Google 2단계 인증을 켠 뒤 [앱 비밀번호](https://myaccount.google.com/apppasswords)를 생성한다. Career 계정 비밀번호와 Gmail 앱 비밀번호는 서로 다르다. [Google 공식 안내](https://support.google.com/accounts/answer/185833?hl=ko).

`frontend/.env.local`의 기존 메일 설정을 아래 값으로 수정한다. 실제 비밀값은 이 문서나 채팅에 적지 않는다.

```env
CAREER_PUBLIC_URL=http://127.0.0.1:3000
CAREER_MAIL_TRANSPORT=smtp
CAREER_SMTP_HOST=smtp.gmail.com
CAREER_SMTP_PORT=587
CAREER_SMTP_USER=발송용Gmail주소
CAREER_SMTP_PASSWORD=발급한앱비밀번호
CAREER_MAIL_FROM="Career <발송용Gmail주소>"
```

수정 후 로컬 서버를 재시작한다. [Google SMTP 설정](https://developers.google.com/workspace/gmail/imap/imap-smtp)에서 587 STARTTLS를 지원한다.

현재 링크는 로컬 PC용이다. 메일을 이 PC의 브라우저에서 열어야 한다. 외부 기기에서 사용할 때는 먼저 해당 배포 환경에 기능을 배포하고 `CAREER_PUBLIC_URL`도 그 서비스 주소로 설정해야 한다.

## API

| 메서드 | 경로 | 기능 |
|---|---|---|
| GET | `/api/account/email-verification` | 본인 이메일과 선택 인증 여부, 로그인 필요 |
| POST | `/api/account/email-verification` | action=request: 본인 이메일 발송, 로그인 필요 |
| POST | `/api/account/email-verification` | action=confirm, token: 인증 확인, 로그인 불필요 |

메일 발송 설정 오류나 SMTP 거부는 503을 반환하며 성공으로 표시하지 않는다. 메일 링크의 GET 요청만으로는 인증을 완료하지 않아 메일 보안 스캐너의 자동 접근으로 소모되지 않는다.
