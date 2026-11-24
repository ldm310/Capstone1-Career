# 네이버 로그인 설정

1. [NAVER Developers 애플리케이션 등록](https://developers.naver.com/apps/#/register)에서 사용 API로 **네이버 로그인**을 선택합니다.
2. 회원 정보는 **이메일 주소**를 필수로 설정하고 이름 또는 닉네임은 필요한 항목만 선택합니다. 이메일 제공이 없으면 Career 가입을 완료하지 않습니다.
3. 서비스 환경은 **PC 웹**을 선택합니다. 서비스 URL은 `http://127.0.0.1:3000`, Callback URL은 `http://127.0.0.1:3000/api/auth/naver/callback`입니다. 로컬 접속도 이 주소로 통일합니다.
4. 발급된 Client ID와 Client Secret을 아래 로컬 설정 파일에 직접 입력합니다. Secret을 채팅이나 Git에 올리지 않습니다.

`frontend/.env.development.local`:

```env
NAVER_CLIENT_ID=발급받은ClientID
NAVER_CLIENT_SECRET="발급받은ClientSecret"
NAVER_REDIRECT_URI=http://127.0.0.1:3000/api/auth/naver/callback
```

개발 단계에서는 앱 관리 계정 또는 네이버 개발자센터에 등록한 테스트 계정으로 확인합니다. 일반 사용자에게 공개하려면 개발자센터의 검수 절차를 확인합니다.

## 가입과 기존 계정

네이버 공식 가이드에 따라 네이버 가입 직후 별도 Career 비밀번호 입력을 필수로 요구하지 않습니다. 신규 회원은 네이버의 사용자 식별자와 제공된 이메일로 가입·로그인합니다. 이메일 로그인도 사용하고 싶다면 마이페이지의 선택 비밀번호 설정 링크에서 이메일로 설정할 수 있습니다. 이는 가입 필수 이메일 인증을 추가하는 것이 아닙니다.

기존 이메일·카카오 계정과 이메일이 같아도 자동으로 연결하지 않습니다. 기존 계정으로 로그인하도록 안내합니다. 제공자와 사용자 식별자가 일치하는 연결 계정은 기존 회원 ID로 로그인합니다.

RDS 변경은 `db/migrations/10-naver-login.sql`의 provider 허용 값 확장뿐이며 별도 사용자 RDS는 만들지 않습니다. `setup-community.mjs`에도 포함되어 있습니다. 로그인 토큰은 저장하지 않습니다. OAuth state는 10분 유효한 HttpOnly 쿠키로 검증하며 로그인 후 복귀 주소는 기존 내부 주소 검증을 사용합니다.

## 이후 스테이징에 배포할 때

서비스 URL `https://staging.15-164-137-78.sslip.io`, Callback URL `https://staging.15-164-137-78.sslip.io/api/auth/naver/callback`도 개발자센터에 등록하고 스테이징 환경의 `NAVER_REDIRECT_URI`와 일치시킵니다. 로컬 설정 파일은 배포에 포함되지 않습니다.

## 공식 자료와 버튼 출처

- [로그인 API](https://developers.naver.com/docs/login/api/api.md)
- [개발 가이드](https://developers.naver.com/docs/login/devguide/devguide.md)
- [버튼 가이드 및 원본 애셋](https://developers.naver.com/docs/login/bi/bi.md): 한글 PNG 묶음의 `NAVER_login_Light_KR_green_icon_H48.png`를 원본 그대로 사용합니다.
