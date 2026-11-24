#!/usr/bin/env python3
"""근거 묶음(여러 레포 가능) + 점검 결과 -> stat (키마다 LV 하나).
규칙: 키의 LV = 통과한 근거 중 최고 LV. 기각된 활동은 버리고, 그 활동 때문에 올라간 도구 LV는 원래 LV로 되돌림. 모름은 '정황'으로만 남김.
Usage: python3 to_stat.py <bundle.json> [<bundle2.json> ...] --person <이름> [--verdicts verdicts.json] > stat.json"""
import argparse, json, sys
import keys


def build_stat(bundles, person, verdicts=None):
    """bundles: [bundle dict], verdicts: {(repo, person, key): 'pass'|'reject'|'unsure'} (없으면 전부 통과로 봄)"""
    verdicts = verdicts or {}
    stat, weak = {}, {}

    def put(key, lv, kind, source, ev, by=None):
        cur = stat.get(key)
        if cur is None or lv > cur['lv']:
            stat[key] = dict(lv=lv, kind=kind, source=source, by=by, evidence=[ev] + ([] if cur is None else cur['evidence'][:2]))
        elif ev not in cur['evidence'] and len(cur['evidence']) < 3: cur['evidence'].append(ev)

    for b in bundles:
        repo = b['meta']['repo']
        for e in b['evidence']:
            if e['person'] != person: continue
            v = verdicts.get((repo, person, e['key']), 'pass')
            ev = dict(repo=repo, where=e['where'])
            if e['kind'] == 'activity':
                if v == 'reject': continue
                if v == 'unsure': weak[e['key']] = dict(claimed_lv=e['lv'], evidence=[ev], reason='점검에서 모름'); continue
                put(e['key'], e['lv'], 'activity', 'own', ev)
            else:
                lv, by = e['lv'], e.get('lifted_by')
                if by and verdicts.get((repo, person, by), 'pass') != 'pass':        # 올려 준 활동이 통과 못 했으면 원래 LV로
                    lv, by = e.get('own_lv', 0), None
                    ev = dict(repo=repo, where=e.get('own_where', e['where']))
                if lv <= 0: continue
                put(e['key'], lv, 'tool', 'lifted' if by else 'own', dict(ev, where=e.get('lifted_where', ev['where']) if by else ev['where']), by)
        for w in b.get('weak', []):
            if w['person'] == person and w['key'] not in stat: weak.setdefault(w['key'], dict(claimed_lv=0, evidence=[dict(repo=repo, where=w['where'])], reason='import·의존성만 있음'))
    for key in list(stat):                                                       # 함께 인정하는 이름
        for imp in keys.IMPLIES.get(key, []):
            s = stat[key]
            if imp not in stat or stat[imp]['lv'] < s['lv']: stat[imp] = dict(lv=s['lv'], kind='tool', source='implied', by=key, evidence=s['evidence'][:1])
    weak = {k: v for k, v in weak.items() if k not in stat}
    return dict(person=person, repos=[b['meta']['repo'] for b in bundles], stat=dict(sorted(stat.items(), key=lambda x: (-x[1]['lv'], x[0]))), weak=weak)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('bundles', nargs='+'); ap.add_argument('--person', required=True); ap.add_argument('--verdicts')
    a = ap.parse_args()
    vd = {}
    if a.verdicts:
        for x in json.load(open(a.verdicts, encoding='utf-8')): vd[(x['repo'], x['person'], x['key'])] = x['verdict']
    json.dump(build_stat([json.load(open(p, encoding='utf-8')) for p in a.bundles], a.person, vd), sys.stdout, ensure_ascii=False, indent=1)
