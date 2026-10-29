"""모든 git 호출의 환경: 사용자 git 설정과 분리하고, 레포의 .mailmap을 끄고, 토큰은 HTTP 헤더로만 넘긴다.

os.environ에서는 PATH·HOME·LANG만 복사한다. Anthropic 키 같은 다른 환경 변수는 git에 넘기지 않는다.
시스템·전역 gitconfig는 읽지 않는다(시스템 설정의 credential.helper=osxkeychain이 401 때 개인 GitHub 자격 증명을 내주고,
전역 url.insteadOf가 개인 SSH 키로 바꿀 수 있다). 설정은 GIT_CONFIG_COUNT·GIT_CONFIG_KEY_n·GIT_CONFIG_VALUE_n 환경 변수로만 건다.
그래서 명령줄(argv)과 .git/config에는 남지 않는다.
"""
import base64
import os

KEEP = ('PATH', 'HOME', 'LANG')


def env(token=None, replace_base=None):
    """git subprocess에 넘길 환경(dict). token이 있으면 github.com 요청에만 HTTP 헤더(basic, x-access-token)로 붙는다.
    replace_base가 있으면 그 이름공간의 replace ref(graft)만 보인다(GIT_REPLACE_REF_BASE).
    GitPython(PyDriller)처럼 os.environ 위에 덮어쓰는 경우에도 자격 증명으로 가는 길은 막힌다: askpass와 -c 설정(GIT_CONFIG_PARAMETERS)을 빈 값으로 둔다."""
    config = [('credential.helper', ''),  # 빈 값은 앞에서 정한 helper를 모두 지운다
              ('core.attributesFile', '/dev/null'),  # 사용자 전역 attributes(~/.config/git/attributes)도 읽지 않는다
              ('mailmap.file', ''), ('mailmap.blob', ''), ('log.mailmap', 'false')]
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
