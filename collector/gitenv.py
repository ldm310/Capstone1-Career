"""모든 git 호출의 환경: 사용자 git 설정과 분리하고, 레포의 .mailmap을 끄고, 토큰은 HTTP 헤더로만 넘긴다.

os.environ에서는 PATH·HOME·LANG만 복사한다. Anthropic 키 같은 다른 환경 변수는 git에 넘기지 않는다.
시스템·전역 gitconfig는 읽지 않는다(시스템 설정의 credential.helper=osxkeychain이 401 때 개인 GitHub 자격 증명을 내주고,
전역 url.insteadOf가 개인 SSH 키로 바꿀 수 있다). 설정은 GIT_CONFIG_COUNT·GIT_CONFIG_KEY_n·GIT_CONFIG_VALUE_n 환경 변수로만 건다.
그래서 명령줄(argv)과 .git/config에는 남지 않는다.
토큰도 여기서 읽는다(github_token): ~/.config/career-stat/github.env의 GITHUB_TOKEN만 쓰고 환경 변수는 보지 않는다.
"""
import base64
import os
import re
from pathlib import Path

KEEP = ('PATH', 'HOME', 'LANG')
# 토큰 파일의 한 줄: [export ]GITHUB_TOKEN=값. 값은 "…"·'…'로 감싸도 되고, 뒤에 # 주석이 와도 된다
TOKEN_LINE = re.compile(r'''\s*(?:export\s+)?GITHUB_TOKEN\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s#"']*))\s*(?:#.*)?''')


class TokenError(RuntimeError):
    """토큰 파일이 없거나 GITHUB_TOKEN 값이 없음. 메시지에 토큰 값은 넣지 않는다."""


def github_token(path: Path = Path.home() / '.config/career-stat/github.env') -> str:
    """서비스 전용 계정(career-stat-bot)의 GitHub 토큰: path 파일의 GITHUB_TOKEN 줄에서만 읽는다.
    환경 변수(GITHUB_TOKEN·GH_TOKEN)는 보지 않는다: 개인 gh 토큰으로 넘어가는 길을 두지 않는다. 빈 줄과 # 주석 줄은 건너뛰고,
    GITHUB_TOKEN 줄이 여럿이면 마지막 줄을 쓴다(셸에서 source한 것과 같다). 파일이나 값이 없으면 TokenError(토큰 없이 돌지 않는다)."""
    try: text = Path(path).read_text(encoding='utf-8-sig')
    except FileNotFoundError: raise TokenError(f'GitHub 토큰 파일이 없습니다: {path}') from None
    except (OSError, UnicodeDecodeError) as e: raise TokenError(f'GitHub 토큰 파일을 읽지 못했습니다({type(e).__name__}): {path}') from None
    token = None
    for line in text.splitlines():
        m = TOKEN_LINE.fullmatch(line)
        if m: token = next(v for v in m.groups() if v is not None)
    if not token: raise TokenError(f'{path}에 GITHUB_TOKEN 값이 없습니다(형식: GITHUB_TOKEN=값)')
    return token


def env(token=None, replace_base=None):
    """git subprocess에 넘길 환경(dict). token이 있으면 github.com 요청에만 HTTP 헤더(basic, x-access-token)로 붙는다.
    replace_base가 있으면 그 이름공간의 replace ref(graft)만 보인다(GIT_REPLACE_REF_BASE).
    GitPython(PyDriller)처럼 os.environ 위에 덮어쓰는 경우에도 자격 증명으로 가는 길은 막힌다: askpass와 -c 설정(GIT_CONFIG_PARAMETERS)을 빈 값으로 둔다."""
    config = [('credential.helper', ''),  # 빈 값은 앞에서 정한 helper를 모두 지운다
              ('core.attributesFile', '/dev/null'),  # 사용자 전역 attributes(~/.config/git/attributes)도 읽지 않는다
              # 설정 파일·blob으로 읽는 .mailmap을 끈다(bare 레포가 기본으로 읽는 HEAD:.mailmap 포함). 작업 트리의 .mailmap은 설정으로 끌 수 없어서
              # clone은 checkout 없이 받는다(extract.sync)
              ('mailmap.file', ''), ('mailmap.blob', ''), ('log.mailmap', 'false'),
              ('core.precomposeUnicode', 'false')]  # macOS clone이 켜 두는 설정: 켜져 있으면 명령줄의 NFD 경로(한글 등)를 NFC로 바꿔 파일을 못 찾는다
    if token:
        basic = base64.b64encode(f'x-access-token:{token}'.encode()).decode()
        config.append(('http.https://github.com/.extraheader', f'AUTHORIZATION: basic {basic}'))
    out = {k: os.environ[k] for k in KEEP if k in os.environ}
    out.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_PARAMETERS='', GIT_TERMINAL_PROMPT='0',
               GIT_ASKPASS='', SSH_ASKPASS='', GIT_LFS_SKIP_SMUDGE='1', GIT_CONFIG_COUNT=str(len(config)))
    for i, (key, value) in enumerate(config):
        out[f'GIT_CONFIG_KEY_{i}'], out[f'GIT_CONFIG_VALUE_{i}'] = key, value
    if replace_base: out['GIT_REPLACE_REF_BASE'] = replace_base
    return out
