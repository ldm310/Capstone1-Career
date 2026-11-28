#!/usr/bin/env python3
"""점검 에이전트 채점. Usage: python3 score_verifier.py --index eval/verifier/testset_index.json <lv3|lv45|b9> <haiku_v2 등 저장된 실행 이름 | 새 verdicts.json>
또는: python3 score_verifier.py <labels.json> <verdicts_a.json> [<verdicts_b.json> ...]
labels: {id: {"wrong": true|false, ...}}. 통과시킨 것 중 맞는 비율(점검 뒤 정밀도), 틀린 것을 걸러낸 비율, 맞는 것을 잘못 기각한 비율을 냄."""
import json, sys


def score(labels, verdicts, unsure_as='drop'):
    v = {x['id']: x['verdict'] for x in verdicts}
    ids = [i for i in labels if i in v]
    wrong = [i for i in ids if labels[i]['wrong']]; good = [i for i in ids if not labels[i]['wrong']]
    kept = [i for i in ids if v[i] == 'pass' or (v[i] == 'unsure' and unsure_as == 'keep')]
    caught = [i for i in wrong if i not in kept]; lost = [i for i in good if i not in kept]
    return dict(n=len(ids), wrong=len(wrong), caught=len(caught), missed=[i for i in wrong if i in kept], false_reject=lost,
                precision_before=round(len(good) / len(ids), 4), precision_after=round(sum(1 for i in kept if not labels[i]['wrong']) / max(len(kept), 1), 4),
                catch_rate=round(len(caught) / max(len(wrong), 1), 4), false_reject_rate=round(len(lost) / max(len(good), 1), 4),
                unsure=sum(1 for i in ids if v[i] == 'unsure'))


if __name__ == '__main__':
    if sys.argv[1] == '--index':      # python3 score_verifier.py --index testset_index.json <lv3|lv45|b9> <저장된 실행 이름 | 새 verdicts.json ...>
        items = json.load(open(sys.argv[2], encoding='utf-8'))['sets'][sys.argv[3]]; labels = {x['id']: dict(wrong=x['label'] == 'wrong') for x in items}
        if sys.argv[4].endswith('.json'): vs = [y for p in sys.argv[4:] for y in json.load(open(p, encoding='utf-8'))]
        else: vs = [dict(id=x['id'], verdict=x['verdicts'][sys.argv[4]]) for x in items]
        r = score(labels, vs, 'drop')
        print(f"{r['n']}건 중 틀림 {r['wrong']} | 걸러냄 {r['caught']}/{r['wrong']} | 맞는 것 중 빠진 것 {len(r['false_reject'])}/{r['n'] - r['wrong']} | 맞는 비율 {r['precision_before']:.1%} -> {r['precision_after']:.1%}"); sys.exit()
    labels = json.load(open(sys.argv[1], encoding='utf-8')); vs = []
    for p in sys.argv[2:]: vs += json.load(open(p, encoding='utf-8'))
    for mode in ('drop', 'keep'):
        r = score(labels, vs, mode)
        print(f"[모름을 {'정황으로 내림' if mode == 'drop' else '통과로 둠'}] {r['n']}건 중 틀림 {r['wrong']} | 걸러냄 {r['caught']}/{r['wrong']} ({r['catch_rate']:.0%}) | 맞는 것 잘못 기각 {len(r['false_reject'])} ({r['false_reject_rate']:.1%}) | 맞는 비율 {r['precision_before']:.1%} -> {r['precision_after']:.1%} | 모름 {r['unsure']}")
        print('   놓친 것:', r['missed'], '| 잘못 기각:', r['false_reject'])
