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
MAX_BLOB = 512 * 1024  # 이 크기 이상인 파일은 세지 않는다. 부분 clone(--filter=blob:limit=512k)이 받지 않는 blob과 정확히 같다
HEAD_BYTES = 64 * 1024  # generated가 보는 blob 앞부분
# 긴 줄 규칙(minified 판별)에서 빼는 확장자: 노트북은 base64 출력이 한 줄이고, 한글 문서는 한 글자가 3바이트라 줄이 길어 보인다
LONG_LINE_EXT = ('.ipynb', '.md', '.markdown', '.rst', '.txt')
BINARY_SCAN = 8000  # 이 앞에 NUL 바이트가 있으면 바이너리(git과 같은 기준)
# 앞 5줄 안에 있으면 생성 파일인 표지(대소문자 구분): 생성 코드 표지와 SQL 덤프 도구가 머리말에 남기는 글귀
MARKERS = (b'@generated', b'DO NOT EDIT', b'-- MySQL dump', b'-- MariaDB dump', b'-- PostgreSQL database dump', b'-- phpMyAdmin SQL Dump')
# SQL 덤프 판별(규칙 ②): 아래 정규식은 모두 앞 64KB를 소문자로 바꾼 글에 쓴다(re.I보다 훨씬 빠르다)
SQL_INTO = re.compile(rb'insert[ \t]+into')  # 사전 검사: 이 글귀가 한 번도 없으면 ②는 보지 않는다
SQL_ROW = re.compile(rb'^[ \t]*(?:insert[ \t]+into\b|\(.*\)[,;][ \t]*\r?$)', re.M)  # INSERT INTO 줄, 또는 VALUES 튜플 줄 (..), (..);
SQL_FILLED = re.compile(rb'^[^\S\n]*\S', re.M)  # 비어 있지 않은 줄(공백·탭·\r뿐인 줄은 아니다)
SQL_DDL = re.compile(rb'^[ \t]*(?:create|alter)[ \t]+table\b', re.M)  # 테이블 정의


def skipped(p, size):
    """경로와 크기만으로 빼는 파일: 너무 큰 파일(512KiB 이상), lock 파일, 빌드·의존성 폴더 안, 이미지·컴파일 결과물 같은 확장자."""
    parts = p.split('/')
    return (size >= MAX_BLOB or parts[-1] in SKIP_NAMES or any(d in SKIP_DIRS for d in parts[:-1])
            or parts[-1].lower().endswith(SKIP_EXT))


def line_count(data):
    """줄 수: 줄바꿈 수 + 줄바꿈 없이 끝나는 마지막 줄(git blame이 세는 방식)."""
    return data.count(b'\n') + (1 if data and not data.endswith(b'\n') else 0)


def sql_dump(head):
    """SQL 덤프인가: 앞 64KB에서 INSERT INTO 줄과 VALUES 튜플 줄이 비어 있지 않은 줄의 60% 이상이다.
    CREATE TABLE·ALTER TABLE이 있으면 그런 줄이 50줄 이상일 때만 덤프로 본다(짧은 schema.sql·시드는 직접 쓴 파일이라 남긴다).
    줄을 파이썬으로 돌지 않고 정규식이 C에서 센다. insert into가 한 번도 안 나오면 세지 않는다."""
    low = head.lower()
    if not SQL_INTO.search(low): return False
    rows, filled = len(SQL_ROW.findall(low)), len(SQL_FILLED.findall(low))
    return filled > 0 and 10 * rows >= 6 * filled and (rows >= 50 or not SQL_DDL.search(low))


def generated(path, head, lines=None):
    """내용으로 빼는 데이터·생성 파일. head = blob 앞 64KB(바이트). 아래 중 하나면 True다.
    ⓪ 앞 8000바이트 안에 NUL 바이트(바이너리·UTF-16 텍스트. 확장자와 상관없이 적용)
    ① 줄 평균 길이 > 300바이트(minified. 노트북·문서는 이 규칙에서 뺀다)
    ② SQL 덤프(sql_dump): 앞 64KB 전체에서 INSERT INTO 줄·VALUES 튜플 줄이 60% 이상이고, 테이블 정의가 있으면 50줄 이상일 때만
    ③ 앞 5줄 안에 MARKERS의 글귀(@generated, DO NOT EDIT, mysqldump·pg_dump·phpMyAdmin 머리말. 대소문자 구분)
    lines = head의 줄 수. 호출하는 쪽이 이미 셌으면 넘겨서 다시 세지 않는다."""
    if not head: return False
    if b'\x00' in head[:BINARY_SCAN]: return True
    top = b'\n'.join(head.split(b'\n', 5)[:5])
    if any(m in top for m in MARKERS): return True
    if sql_dump(head): return True
    if path.lower().endswith(LONG_LINE_EXT): return False
    return len(head) > 300 * (line_count(head) if lines is None else lines)
