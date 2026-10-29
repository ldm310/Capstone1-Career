"""흐름 3단계: 본인 줄에서 평가할 기술 후보를 찾는다(LLM 없음).

근거는 세 가지다: 본인 줄이 있는 파일의 확장자(언어), 본인 줄의 import, 본인이 쓴 의존성 파일 줄.
기술 이름은 팀 사전(capabilities.json)의 표준 이름으로 맞추고, 사전에 없는 이름은 따로 남긴다.
기준표상 import·설치만으로는 LV0도 아니다. 여기서는 평가 대상만 고른다.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import gitenv  # git 읽기도 사용자 설정과 분리한다(부분 clone에서 없는 blob을 내려받을 때 개인 자격 증명이 쓰이지 않게)

DICTIONARY = Path(__file__).resolve().parent.parent / '04-repo' / 'feature-job-skill@4957696' / 'job-skill' / 'capabilities.json'
EXT = {'.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript', '.mjs': 'JavaScript', '.ts': 'TypeScript', '.tsx': 'TypeScript',
       '.java': 'Java', '.kt': 'Kotlin', '.go': 'Go', '.rs': 'Rust', '.c': 'C', '.h': 'C', '.cpp': 'C++', '.cc': 'C++', '.hpp': 'C++',
       '.cs': 'C#', '.php': 'PHP', '.swift': 'Swift', '.sql': 'SQL', '.html': 'HTML', '.css': 'CSS', '.sh': 'Shell'}
# import·패키지 이름이 사전 이름과 다른 경우만 적는다(제안, 계속 보강). 같으면 사전 대조로 바로 잡힌다.
ALIAS = {'torch': 'PyTorch', 'cv2': 'OpenCV', 'sklearn': 'scikit-learn', 'np': 'NumPy', 'numpy': 'NumPy', 'psycopg2': 'PostgreSQL',
         'psycopg': 'PostgreSQL', 'pg': 'PostgreSQL', 'pymysql': 'MySQL', 'mysql2': 'MySQL', 'mysqlclient': 'MySQL', 'boto3': 'AWS',
         'pyspark': 'Spark', 'airflow': 'Apache Airflow', 'mongoose': 'MongoDB', 'pymongo': 'MongoDB', 'next': 'Next.js',
         'rclpy': 'ROS 2', 'faster_whisper': 'Whisper', 'whisper': 'Whisper', '@nestjs': 'NestJS', '@angular': 'Angular',
         '@supabase': 'Supabase', '@tanstack/react-query': 'Tanstack Query', '@aws-sdk': 'AWS', '@prisma/client': 'Prisma'}
JAVA_PREFIX = [('org.springframework.boot', 'Spring Boot'), ('org.springframework.security', 'Spring Security'),
               ('org.springframework', 'Spring'), ('jakarta.persistence', 'JPA'), ('javax.persistence', 'JPA'),
               ('org.apache.ibatis', 'MyBatis'), ('com.querydsl', 'QueryDSL'), ('org.hibernate', 'Hibernate')]
NOT_CODE = {'.md', '.txt', '.json', '.yml', '.yaml', '.toml', '.cfg', '.ini', '.lock', '.gitignore', '.env', ''}


def norm(s): return re.sub(r'[\s_.\-]', '', s.lower())


def dictionary_version(path=DICTIONARY):
    """사전 버전: capabilities.json version의 첫 토큰(예: 0.1.1). job-skill이 job.dictionary_version·extraction_run.dict_version에 넣는 값과 같다."""
    v = json.loads(Path(path).read_text()).get('version') or ''
    return v.split()[0] if v else ''


def load_dictionary(path=DICTIONARY):
    d = json.loads(Path(path).read_text())
    index = {norm(a): name for name, v in d['techs'].items() for a in [name, *v.get('aliases', [])]}
    return index, d['techs']


def resolve(raw, index):
    """import·패키지 이름 → (표준 이름, 사전에 있는지). scoped npm 패키지(@scope/name)는 전체 → scope → name 순서로 찾는다."""
    scope, _, rest = raw.partition('/') if raw.startswith('@') else ('', '', '')
    for key in filter(None, (raw, scope)):
        if key in ALIAS:
            name = ALIAS[key]
            return (index.get(norm(name)), True) if index.get(norm(name)) else (name, False)
    for key in filter(None, (raw, rest, scope.lstrip('@'))):
        if index.get(norm(key)): return index[norm(key)], True
    return raw, False


def used_names(path, text):
    """본인 줄 한 줄에서 쓰는 외부 이름(import·require·의존성 선언)."""
    suffix, name = Path(path).suffix, Path(path).name
    out = []
    pkg = lambda p: '/'.join(p.split('/')[:2]) if p.startswith('@') else p.split('/')[0]  # scoped 패키지는 @scope/name을 남긴다
    if suffix == '.py':
        m = re.match(r'\s*from\s+([\w.]+)\s+import', text)
        if m and not m.group(1).startswith('.'): out.append(m.group(1).split('.')[0])  # 상대 import는 레포 안 모듈
        m = re.match(r'\s*import\s+([\w.,\s]+?)\s*(?:#.*)?$', text)
        if m: out += [n.split()[0].split('.')[0] for n in m.group(1).split(',') if n.strip()]  # import a, b as c
    elif suffix in ('.js', '.jsx', '.mjs', '.ts', '.tsx'):
        for m in re.finditer(r'''(?:\bfrom\s+|\brequire\(\s*|\bimport\s+)['"]([^'"./][^'"]*)['"]''', text):
            out.append(pkg(m.group(1)))
    elif suffix == '.java':
        m = re.match(r'\s*import\s+(?:static\s+)?([\w.]+?)(?:\.\*)?\s*;', text)
        if m: out += [tech for prefix, tech in JAVA_PREFIX if m.group(1).startswith(prefix)][:1]
    elif re.fullmatch(r'requirements[\w.-]*\.txt', name):
        line = text.strip()
        m = re.match(r'([A-Za-z0-9_.\-]+)', line)
        if m and not line.startswith(('#', '-', 'git+')) and '://' not in line: out.append(m.group(1).lower().replace('-', '_'))
    elif name == 'package.json':
        m = re.match(r'\s*"(@?[\w.\-/]+)"\s*:\s*"[\^~>=<\d*]', text)
        if m: out.append(pkg(m.group(1)))
    elif name in ('build.gradle', 'build.gradle.kts', 'pom.xml'):
        out += [tech for prefix, tech in JAVA_PREFIX if prefix in text][:1]
    return out


def split_lines(raw):
    """git blame과 같은 줄 번호가 되도록 '\\n'으로만 나눈다(str.splitlines는 \\x0c·\\u2028 등에서도 끊어 번호가 밀린다).
    바이트로 받아 나눈다: 텍스트 모드로 읽으면 Python이 혼자 있는 \\r도 줄바꿈으로 바꿔 번호가 밀린다."""
    lines = [l.removesuffix('\r') for l in raw.decode('utf-8', 'replace').split('\n')]
    return lines[:-1] if lines and lines[-1] == '' else lines


def file_lines(repo_path, sha, path):
    r = subprocess.run(['git', '-C', str(repo_path), 'show', f'{sha}:{path}'], capture_output=True, env=gitenv.env())
    return split_lines(r.stdout) if r.returncode == 0 else []


def read_files(repo_path, sha, paths, chunk=500):
    """여러 파일을 git cat-file 한 번(묶음마다)으로 읽어 {경로: file_lines와 같은 줄 목록}을 돌려준다. 없는 파일은 []."""
    out = {}
    paths = [p for p in dict.fromkeys(paths)]
    for p in [p for p in paths if '\n' in p]: out[p] = file_lines(repo_path, sha, p)  # 줄바꿈이 든 경로는 묶음 입력에 못 넣는다
    batch = [p for p in paths if '\n' not in p]
    for k in range(0, len(batch), chunk):
        part = batch[k:k + chunk]
        raw = subprocess.run(['git', '-C', str(repo_path), 'cat-file', '--batch'], input=''.join(f'{sha}:{p}\n' for p in part).encode(),
                             capture_output=True, env=gitenv.env()).stdout
        i = 0
        for p in part:
            j = raw.index(b'\n', i)
            head = raw[i:j].split()
            if len(head) != 3 or head[1] != b'blob': out[p], i = [], j + 1; continue  # missing·ambiguous·폴더
            size = int(head[2])
            out[p], i = split_lines(raw[j + 1:j + 1 + size]), j + 2 + size
    return {p: out[p] for p in paths}


def detect(repo_path, sha, units, index):
    """units: 이 commit의 본인 줄 증거 단위 [{path, lines}] → {skills, unmatched}."""
    skills, unmatched = {}, {}
    tree = subprocess.run(['git', '-C', str(repo_path), 'ls-tree', '-r', '-z', '--name-only', sha], capture_output=True, text=True,
                          env=gitenv.env()).stdout.split('\0')
    # 레포 안 Python 모듈은 기술이 아니다: .py 파일 이름과 .py가 든 폴더 이름만 센다(react.svg 같은 파일 이름으로 React를 버리지 않게)
    local = {part for p in tree if p.endswith('.py') for part in [Path(p).stem, *Path(p).parent.parts]}

    def add(tech, known, path, ranges, signal):
        s = skills.setdefault(tech, dict(in_dictionary=known, files={}, signals=set()))
        s['files'][path] = ranges
        s['signals'].add(signal)

    texts = {}
    for k, u in enumerate(units):
        if k % 500 == 0: texts = read_files(repo_path, sha, [x['path'] for x in units[k:k + 500]])  # 500개씩 한 번에 읽는다(메모리 상한)
        path, ranges = u['path'], u['lines']
        suffix = Path(path).suffix.lower()
        if suffix in EXT:
            tech, known = resolve(EXT[suffix], index)
            add(tech, known, path, ranges, f'확장자 {suffix}')
        lines = texts[path]
        for s, e in ranges:
            for text in lines[s - 1:e]:
                for raw in used_names(path, text):
                    if suffix == '.py' and (raw in sys.stdlib_module_names or raw == '__future__' or (raw in local and raw not in ALIAS)): continue
                    tech, known = resolve(raw, index)
                    if known or raw in ALIAS or raw.partition('/')[0] in ALIAS:
                        add(tech, known, path, ranges, f'import {raw}' if suffix not in NOT_CODE else f'의존성 {raw}')
                    else: unmatched[raw] = unmatched.get(raw, 0) + 1
    for s in skills.values():
        s['own_lines'] = sum(e - b + 1 for ranges in s['files'].values() for b, e in ranges)
        s['signals'] = sorted(s['signals'])
    return dict(skills=skills, unmatched=dict(sorted(unmatched.items(), key=lambda kv: -kv[1])))
