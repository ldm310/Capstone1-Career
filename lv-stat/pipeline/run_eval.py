#!/usr/bin/env python3
"""run_v3.py run|audit|recall <repos_dir> [seed]"""
import collections, json, os, random, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract as v
import lv_dict as D
b = v.b
mode, R = sys.argv[1], os.path.abspath(sys.argv[2]); OUT = R.rstrip('/') + '_v4.json'
NODE = {'fs', 'path', 'http', 'https', 'crypto', 'os', 'util', 'events', 'stream', 'url', 'child_process', 'assert', 'zlib', 'net', 'buffer', 'process', 'readline', 'worker_threads', 'timers', 'module', 'vm', 'dns', 'tls', 'cluster'}
repos = sorted(d for d in os.listdir(R) if os.path.isdir(os.path.join(R, d, '.git')))
show = lambda repo, p: subprocess.run(['git', 'show', f'HEAD:{p}'], cwd=os.path.join(R, repo), capture_output=True, text=True).stdout

def coverage(repo):
    path = os.path.join(R, repo); files = [p for p in b.head_files(path) if v.fkind(p) == 'code']
    texts = {p: show(repo, p) for p in files}; pk = set()
    for t in texts.values():
        m = re.search(r'^package\s+([\w.]+)', t, re.M)
        if m: pk.add('.'.join(m.group(1).split('.')[:2]))
    top = {q for p in files for q in p.split('/')[:-1]} | {os.path.splitext(os.path.basename(p))[0] for p in files}
    alias = set()        # tsconfig paths·workspace 패키지 이름 = 내부 모듈
    for q in b.head_files(path):
        base = os.path.basename(q)
        if re.fullmatch(r'[tj]sconfig[\w.-]*\.json', base):
            for m in re.finditer(r'"((?:@|~|#)?[\w.-]*(?:/[\w.-]+)*)(?:/\*)?"\s*:\s*\[', show(repo, q)): alias.add(m.group(1))
        elif base == 'package.json':
            m = re.search(r'^\s{0,4}"name"\s*:\s*"([^"]+)"', show(repo, q), re.M)
            if m: alias.add(m.group(1))
    alias.discard('')
    tot = known = 0; unk = collections.Counter()
    for p, t in texts.items():
        ext = os.path.splitext(p)[1]
        for line in t.splitlines():
            s = line.strip()
            if ext in ('.java', '.kt'):
                m = re.match(r'import\s+(?:static\s+)?([\w.]+)', s)
                if not m: continue
                mod = m.group(1)
                if mod.startswith(('java.', 'javax.crypto', 'javax.sql', 'javax.net', 'javax.imageio', 'javax.xml', 'kotlin.')) or any(mod.startswith(x) for x in pk): continue
                eco, key = 'java', '.'.join(mod.split('.')[:3])
            elif ext == '.py':
                m = re.match(r'(?:from|import)\s+([\w.]+)', s)
                if not m or m.group(1).startswith('.'): continue
                mod = m.group(1); root = mod.split('.')[0]
                if root in sys.stdlib_module_names or root in top or root == '__future__': continue
                eco, key = 'py', root
            else:
                m = re.search(r'''(?:from\s+|require\(\s*|^import\s+)['"]([^'"]+)['"]''', s)
                if not m or m.group(1).startswith(('.', '@/', '~/', 'src/', '#')): continue
                mod = m.group(1); root = '/'.join(mod.split('/')[:2]) if mod.startswith('@') else mod.split('/')[0]
                if root.replace('node:', '') in NODE or root.startswith('node:') or root in top: continue
                if any(mod == x or mod.startswith(x + '/') for x in alias): continue
                eco, key = 'js', root
            tot += 1
            if D.lookup(eco, mod) is not None: known += 1
            else: unk[key] += 1
    return tot, known, unk

if mode == 'run':
    out = {'rows': [], 'meta': {}, 'cov': {}}
    for repo in repos:
        t0 = time.time(); res, weak, meta = v.analyze(os.path.join(R, repo)); dt = time.time() - t0
        for (d, k), x in res.items(): out['rows'].append(dict(repo=repo, dev=d, key=k, lv=x['lv'], ev=x['where'], n=x['n'], **{k2: x[k2] for k2 in ('kind', 'lifted_by', 'own_lv', 'lifted_where') if k2 in x}))
        for (d, k), e in weak.items(): out['rows'].append(dict(repo=repo, dev=d, key=k, lv=0, ev=e, n=1))
        tot, known, unk = coverage(repo); out['meta'][repo] = meta; out['cov'][repo] = dict(tot=tot, known=known, unk=unk.most_common(15))
        n = collections.Counter(r['lv'] for r in out['rows'] if r['repo'] == repo)
        print(f"{repo[:40]:40} {dt:5.1f}s 사람 {len(meta['people'])} | LV1 {n[1]:3} LV2 {n[2]:3} LV3 {n[3]:2} LV4+ {n[4] + n[5]:2} 정황 {n[0]:3} | 사전 {100 * known // max(tot, 1)}% ({known}/{tot}) | 묶음 {meta['merged']} AI {meta['ai']} 생성기 파일 {len(meta['generated'])}")
        if unk: print('      사전에 없음:', ', '.join(f'{k}({c})' for k, c in unk.most_common(10)))
    T = sum(c['tot'] for c in out['cov'].values()); K = sum(c['known'] for c in out['cov'].values())
    print(f'\n사전 도달률 합계 {K}/{T} = {100 * K / max(T, 1):.0f}%')
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def line_of(repo, ev):
    outl = []
    for m in re.finditer(r'(\S+?):(\d+)', ev):
        try: outl.append(show(repo, m.group(1)).splitlines()[int(m.group(2)) - 1].strip()[:105])
        except Exception: outl.append('?')
    return ' ‖ '.join(outl)

if mode == 'audit':
    rows = [r for r in json.load(open(OUT, encoding='utf-8'))['rows'] if r['lv']]
    BASE = {'Git', 'Java', 'Kotlin', 'Python', 'JavaScript', 'TypeScript', 'AI 코딩 도구'}
    ACT2 = {'API 개발', '외부 API 연동', '테스트 코드', 'SQL'}; CFG = {'Docker', 'GitHub Actions', 'Nginx', 'Kubernetes', 'Prisma'}
    sec = lambda r: 'L3' if r['lv'] >= 3 else 'ACT' if r['key'] in ACT2 else 'CFG' if r['key'] in CFG else 'BASE' if r['key'] in BASE else 'TOOL'
    cnt = collections.Counter(sec(r) for r in rows); print('판정 수', dict(cnt))
    for name in ('L3', 'ACT'):
        print(f'\n=== {name}')
        pool = [r for r in rows if sec(r) == name]; random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
        if len(pool) > 60: print(f'   ({len(pool)}개 중 무작위 60개)'); pool = random.sample(pool, 60)
        for r in pool:
            if True: print(f"LV{r['lv']} {r['repo'][:12]:12} {r['dev'][:10]:10} {r['key'][:9]:9} | {r['ev'][-78:]} | {line_of(r['repo'], r['ev'])}")
    tools = [r for r in rows if sec(r) == 'TOOL']; random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    print(f'\n=== TOOL {len(tools)}개 중 표본 40')
    for r in random.sample(tools, min(40, len(tools))): print(f"LV{r['lv']} {r['repo'][:12]:12} {r['dev'][:10]:10} {r['key'][:14]:14} | {r['ev'][-50:]} | {line_of(r['repo'], r['ev'])}")
    print('\n=== CFG'); print(' / '.join(f"{r['repo'][:8]}·{r['dev'][:8]}·{r['key']}·{r['ev'].split('/')[-1]}" for r in rows if sec(r) == 'CFG'))

if mode == 'recall':
    rows = [r for r in json.load(open(OUT, encoding='utf-8'))['rows'] if r['lv']]
    CAT = [
     ('API 엔드포인트', 'API 개발', None, r'@(Get|Post|Put|Delete|Patch|Request)Mapping|@(Get|Post|Put|Delete|Patch)\(|@\w+\.(get|post|put|delete|patch|route)\(|\b\w*(app|[rR]outer)\.(get|post|put|delete|patch)\(', True),
     ('테스트 코드', '테스트 코드', r'(^|/)(tests?|__tests__)/|Tests?\.(java|kt)$|\.(test|spec)\.[jt]sx?$', r'@Test\b|def test_|\b(it|test)\(', False),
     ('Docker', 'Docker', r'(^|/)(Dockerfile[\w.]*|(docker-)?compose[\w.-]*\.ya?ml)$', r'.', False),
     ('CI workflow', 'GitHub Actions', r'^\.github/workflows/', r'.', False),
     ('CI/CD(배포)', 'CI/CD 구축', r'^\.github/workflows/', r'docker push|ssh|scp|kubectl|aws |rsync|gcloud|flyctl|vercel|netlify|gh-pages|deploy-pages|push: true', False),
     ('외부 API 호출', '외부 API 연동', None, r'RestTemplate|WebClient|RestClient|\brequests\.(get|post)|httpx\.|axios\.|FeignClient|aiohttp', True),
     ('SQL', 'SQL', None, r'\b(SELECT|INSERT INTO|CREATE TABLE|ALTER TABLE)\b', True),
     ('DB 스키마', 'DB 설계', None, r'CREATE TABLE|op\.create_table|^model \w+ \{|@Entity\b|__tablename__|models\.Model', True),
     ('인덱스', '쿼리 튜닝', None, r'CREATE INDEX|@Index\(|index=True|op\.create_index|@@index|db_index', True),
     ('OAuth', 'OAuth 연동', None, r'oauth2Login|OAuth2User|kauth\.kakao|passport-|next-auth|authorization_code|accounts\.google\.com/o/oauth', True),
     ('결제', '결제 연동', None, r'tosspayments|iamport|portone|paymentKey|api\.stripe', True),
     ('캐시', '캐시 도입', None, r'@Cacheable|caffeine|cachetools|lru-cache|node-cache|CACHE_TTL|cache_ttl|TTLCache', True),
     ('메시지·작업 큐', '메시지 큐', None, r'[Kk]afka|[Rr]abbit[Mm][Qq]|\bnats\b|\bcelery\b|bullmq|\bsqs\b', True),
     ('모니터링', '모니터링 설정', None, r'prometheus|grafana|sentry|micrometer|opentelemetry', True),
     ('JWT', 'JWT', None, r'jsonwebtoken|\bjwt\b|JWT', True), ('Redis', 'Redis', None, r'[Rr]edis', True), ('MongoDB', 'MongoDB', None, r'pymongo|motor|mongoose|MongoRepository', True),
     ('WebSocket', 'WebSocket', None, r'WebSocket|websocket|socket\.io', True), ('클라우드 SDK', 'AWS SDK', None, r'boto3|aws-sdk|@aws-sdk|S3Client|AmazonS3', True),
    ]
    EXT = ('.java', '.kt', '.py', '.js', '.ts', '.tsx', '.jsx', '.sql', '.yml', '.yaml', '.prisma')
    print(f"{'':16}" + ' '.join(r[-8:] for r in repos)); miss = []; tot = collections.Counter(); hit = collections.Counter()
    grid = collections.defaultdict(dict)
    for repo in repos:
        files = [f for f in b.head_files(os.path.join(R, repo)) if (f.endswith(EXT) or os.path.basename(f).startswith('Dockerfile')) and not re.search(r'(^|/)(node_modules|dist|build|docs?)/|lock', f)]
        text = {f: show(repo, f) for f in files}; keys = {r['key'] for r in rows if r['repo'] == repo}
        for name, key, prx, crx, notest in CAT:
            n = 0; ex = ''
            for f, t in text.items():
                if prx and not re.search(prx, f): continue
                if notest and re.search(r'test|spec', f, re.I): continue
                h = [l.strip() for l in t.splitlines() if re.search(crx, l)]
                n += len(h)
                if h and not ex: ex = f'{f[-40:]}: {h[0][:70]}'
            grid[name][repo] = (n, key in keys, ex)
    for name, key, *_ in CAT:
        cells = []
        for repo in repos:
            n, got, ex = grid[name][repo]
            cells.append('   -    ' if not n and not got else f"{'O' if got else 'X'}{n:<7}")
            if n and not got: miss.append((name, repo, n, ex))
            if got and not n: miss.append((name + '(도구만 잡음)', repo, 0, ''))
        print(f'{name:16}' + ' '.join(cells))
    print('\nX(넓은 검색엔 있는데 도구가 못 잡음) — 직접 확인 필요:')
    for name, repo, n, ex in miss: print(f'  {name:14} {repo[-22:]:22} {n:4}줄  {ex}')
