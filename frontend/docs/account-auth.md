# 회원가입과 비밀번호 복구

회원은 이메일과 Career 비밀번호를 갖는다. 일반 이메일 가입에 이메일 인증번호나 인증 메일 확인 단계를 추가하지 않는다.

## 카카오 가입

1. 카카오 OAuth state를 확인하고 토큰 교환 및 사용자 정보 조회를 완료한다.
2. 새 회원이면 계정을 즉시 만들지 않고 10분 유효한 일회용 가입 정보를 서버에 보관한다.
3. `/sign-in?provider=kakao`에 카카오 이메일과 이름을 표시한다. 이메일은 읽기 전용이며 서버도 변경 요청을 거부한다.
4. 비밀번호와 확인을 입력한 뒤 회원과 카카오 식별자 연결을 함께 저장한다. 가입 전에는 로그인 세션이 없다.
5. 기존 카카오 전용 회원은 동일한 회원 ID를 유지하고 한 번 비밀번호를 설정한다. 이후에는 카카오 또는 이메일·비밀번호로 로그인한다.

같은 이메일의 기존 일반 계정에 카카오를 이메일만 보고 자동 연결하지 않는다.
카카오 회원 식별자와 이메일 유효·인증 상태는 [카카오 공식 사용자 정보 및 보안 안내](https://developers.kakao.com/docs/ko/getting-started/security-guideline)를 따른다.

DB 추가: `db/migrations/09-kakao-password-setup.sql`. `career_account_oauth.password_set_at`이 NULL인 기존 카카오 계정은 설정이 필요하다.
일반 회원의 기존 비밀번호는 변경하지 않는다. SQLite OAuth 캐시에는 같은 목적의 컬럼을 멱등 추가한다.

## 세션과 비밀번호

세션은 인증 당시 비밀번호 해시의 지문을 보관한다. 요청마다 현재 비밀번호의 지문과 비교해,
비밀번호가 바뀌면 다른 저장소에 남은 오래된 세션도 사용할 수 없도록 한다. 해시나 지문은 사용자 응답에 포함하지 않는다.
로그인 중 비밀번호 변경은 다른 세션을 모두 종료하고 현재 브라우저의 세션을 새로 발급한다.
계정 복구는 모든 세션을 종료하며 자동 로그인하지 않는다. 프로필 수정은 비밀번호 해시를 덮어쓰지 않는다.
새 지문 컬럼이 없던 구버전 세션은 한 번 다시 로그인해야 한다.

## 비밀번호 찾기

`/forgot-password`에서 이메일을 입력하면 계정 유무와 무관한 동일한 안내를 반환한다.
가입된 계정에만 30분 유효한 일회용 링크를 발송한다. 링크 토큰은 DB에 해시로만 저장하며
비밀번호·이메일이 변경됐거나 이미 사용했으면 거부한다. URL fragment로 전달해 서버 접근 로그에 토큰을 남기지 않는다.
이메일 가입 인증과 별개인 계정 복구 절차다. [OWASP 비밀번호 복구 지침](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)을 참고한다.

### 로컬 메일함

로컬 `.env.local`:

```env
CAREER_PUBLIC_URL=http://127.0.0.1:3000
CAREER_MAIL_TRANSPORT=file
```

메일은 `CAREER_DATA_DIR/mailbox/` 또는 `frontend/.career-data/mailbox/`에 JSON과 HTML로 저장한다.
HTML 파일을 브라우저에서 열어 재설정 버튼으로 진행한다. 메일함은 HTTP API나 공개 파일 경로로 제공하지 않는다.
file 방식은 loopback 주소에서만 허용한다. 실제 이메일은 발송하지 않는다.

### 실제 발송을 연결할 때

`CAREER_MAIL_TRANSPORT=smtp`와 아래 환경 설정을 사용한다. 비밀값을 코드나 저장소에 넣지 않는다.

```env
CAREER_PUBLIC_URL=https://실제서비스주소
CAREER_SMTP_HOST=메일서버주소
CAREER_SMTP_PORT=587
CAREER_SMTP_USER=발송계정
CAREER_SMTP_PASSWORD=발송비밀번호
CAREER_MAIL_FROM=Career <발송이메일>
```

465는 TLS, 587 등은 STARTTLS를 요구한다. [Nodemailer SMTP 설정](https://nodemailer.com/smtp)을 참고한다.
설정이 없으면 발송 완료로 가장하지 않고 서비스 준비 안내를 반환한다.

## 검증

`npm run test:auth`는 격리 SQLite와 가짜 카카오 HTTP 응답을 사용한다. 실제 카카오·RDS·메일 서비스에 접근하지 않는다.
Windows에서는 `PLAYWRIGHT_CHANNEL=msedge`를 설정할 수 있다.
RDS 검증은 `RUN_RDS_ACCOUNT_TESTS=1`에서 `tests/auth-rds-security.spec.ts`를 실행하며 시험 회원만 생성·정리한다.
