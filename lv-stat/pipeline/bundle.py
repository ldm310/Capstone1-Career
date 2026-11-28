#!/usr/bin/env python3
"""레포 하나 -> 근거 묶음(JSON). 코드는 실행하지 않고 git 기록만 읽음.
Usage: GIT_NO_LAZY_FETCH=1 python3 bundle.py <clone한 레포 폴더> [--name owner/repo] > bundle.json"""
import argparse, json, os, subprocess, sys
import extract


def make_bundle(path, name=None):
    res, weak, meta = extract.analyze(path)
    head = subprocess.run(['git', '-C', path, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    ev = []
    for (person, key), x in sorted(res.items(), key=lambda kv: (kv[0][0], -kv[1]['lv'], kv[0][1])):
        ev.append(dict(person=person, key=key, kind=x.get('kind', 'tool'), lv=x['lv'], where=x['where'], n=x['n'],
                       **{k: x[k] for k in ('own_lv', 'lifted_by', 'lifted_where') if k in x}))
    return dict(meta=dict(repo=name or os.path.basename(os.path.abspath(path)), head=head, extractor='v4', practice=meta['practice'], people=meta['people'], merged=meta['merged'],
                          ai_commits=meta['ai'], generated_files=len(meta['generated'])),
                evidence=ev, weak=[dict(person=p, key=k, where=w) for (p, k), w in sorted(weak.items())])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('path'); ap.add_argument('--name')
    a = ap.parse_args()
    json.dump(make_bundle(a.path, a.name), sys.stdout, ensure_ascii=False, indent=1)
