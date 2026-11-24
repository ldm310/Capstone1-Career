#!/usr/bin/env python3
"""LV4~5(또는 지정한 키) 판정을 근거 줄과 함께 출력. Usage: python3 audit45.py <repos_dir> [min_lv=4] [ctx=1] [keys,쉼표]"""
import collections, json, re, subprocess, sys
D = sys.argv[1].rstrip('/'); MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 4; CTX = int(sys.argv[3]) if len(sys.argv) > 3 else 1
KEYS = set(sys.argv[4].split(',')) if len(sys.argv) > 4 else None
rows = [r for r in json.load(open(D + '_v4.json'))['rows'] if r['lv'] >= MIN and r.get('kind') == 'activity' and (not KEYS or r['key'] in KEYS)]
print(len(rows), dict(collections.Counter(r['key'] for r in rows)))
for r in sorted(rows, key=lambda r: (r['key'], r['repo'])):
    print(f"## {r['key']} | {r['repo'][:22]} | {r['dev'][:12]} | {r['ev'][-150:]}")
    m = re.match(r'(\S+?):(\d+)', r['ev'])
    if m and CTX >= 0:
        t = subprocess.run(['git', '-C', f"{D}/{r['repo']}", 'show', f'HEAD:{m.group(1)}'], capture_output=True, text=True, errors='replace').stdout.splitlines()
        n = int(m.group(2))
        for i in range(max(0, n - 1 - CTX), min(len(t), n + CTX)): print(f"   {'>' if i + 1 == n else ' '}{i + 1}: {t[i].strip()[:150]}")
