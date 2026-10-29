"""경로·내용 필터: 줄을 세기 전에 빌드 결과물·생성 파일·의존성 폴더를 빼서 누구의 줄로도 세지 않는다.

skipped는 경로와 크기만 본다. generated는 blob 앞 64KB(HEAD_BYTES)의 내용을 본다. 기준은 팀 확정 전이라 제안이다.
"""
import re

SKIP_DIRS = {'node_modules', 'dist', 'build', '.next', 'out', 'vendor', 'venv', '.venv', '__pycache__', 'target', '.gradle', 'coverage',
             'site-packages', '_vendor'}  # 뒤의 둘은 의존성 폴더다(Windows 가상환경의 Lib/site-packages도 site-packages로 걸린다)
SKIP_NAMES = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'Pipfile.lock', 'uv.lock', 'Cargo.lock', 'go.sum', 'gradlew', 'gradlew.bat'}
BUILD_EXT = ('.exe', '.dll', '.so', '.dylib', '.o', '.obj', '.pdb', '.a', '.lib', '.pyc', '.wasm')  # 컴파일 결과물
SKIP_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.pdf', '.zip', '.jar', '.class', '.woff', '.woff2',
            '.ttf', '.eot', '.mp4', '.mp3', '.map', '.min.js', '.min.css', '.bin', '.pt', '.onnx', '.pkl', '.h5', '.db', '.sqlite') + BUILD_EXT
MAX_BLOB = 512 * 1024
HEAD_BYTES = 64 * 1024  # generated가 보는 blob 앞부분
# 긴 줄 규칙(minified 판별)에서 빼는 확장자: 노트북은 base64 출력이 한 줄이고, 한글 문서는 한 글자가 3바이트라 줄이 길어 보인다
LONG_LINE_EXT = ('.ipynb', '.md', '.markdown', '.rst', '.txt')
INSERT = re.compile(rb'\s*INSERT INTO', re.I)


def skipped(p, size):
    """경로와 크기만으로 빼는 파일: 너무 큰 파일, lock 파일, 빌드·의존성 폴더 안, 이미지·컴파일 결과물 같은 확장자."""
    parts = p.split('/')
    return (size > MAX_BLOB or parts[-1] in SKIP_NAMES or any(d in SKIP_DIRS for d in parts[:-1])
            or parts[-1].lower().endswith(SKIP_EXT))


def line_count(data):
    """줄 수: 줄바꿈 수 + 줄바꿈 없이 끝나는 마지막 줄(git blame이 세는 방식)."""
    return data.count(b'\n') + (1 if data and not data.endswith(b'\n') else 0)


def generated(path, head, lines=None):
    """내용으로 빼는 데이터·생성 파일. head = blob 앞 64KB(바이트). 아래 중 하나면 True다.
    ① 줄 평균 길이 > 300바이트(minified. 노트북·문서는 이 규칙에서 뺀다)
    ② 앞 50줄의 60% 이상이 INSERT INTO(SQL 덤프. 직접 쓴 schema.sql은 남는다)
    ③ 앞 5줄 안에 @generated 또는 DO NOT EDIT(대소문자 구분)
    lines = head의 줄 수. 호출하는 쪽이 이미 셌으면 넘겨서 다시 세지 않는다."""
    if not head: return False
    rows = head.split(b'\n', 50)
    if rows[-1] == b'': rows.pop()  # 마지막 줄바꿈 뒤의 빈 조각은 줄이 아니다
    rows = rows[:50]
    top = b'\n'.join(rows[:5])
    if b'@generated' in top or b'DO NOT EDIT' in top: return True
    if 10 * sum(bool(INSERT.match(r)) for r in rows) >= 6 * len(rows): return True
    if path.lower().endswith(LONG_LINE_EXT): return False
    return len(head) > 300 * (line_count(head) if lines is None else lines)
