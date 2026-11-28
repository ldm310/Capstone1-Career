#!/usr/bin/env python3
"""stat x 공고 -> 공고마다 줄별 충족 여부와 '이 공고 기준 내 역량'.
줄 판정(요구 LV = 기술 LV(줄 기준)):
  충족            내 LV >= 요구 LV
  기법 충족       내 LV >= 요구 LV 인데 줄이 규모·운영을 요구함(LV4 이상). 코드로 기법은 확인, 규모·운영은 GitHub로 확인 불가
  부분            근거는 있는데 내 LV < 요구 LV
  미충족          줄의 키에 해당하는 근거가 없음
  판단 불가       줄에서 역량 키를 못 뽑음(도메인·태도 등) 또는 기준표에서 판단 불가
경력 조건(career_rule)은 판정하지 않고 표시만 함.
Usage: python3 match.py <stat.json> ../data/postings.json > match.json"""
import json, sys
import keys

LINE_MODE = 'any'      # 'any': 줄의 키 중 하나라도 충족하면 충족 / 'all': 모두 충족해야 충족


def my_lv(stat, key):
    if key in keys.GROUPS:
        best = max(((stat[m]['lv'], m) for m in keys.GROUPS[key] if m in stat), default=(0, None))
        return best
    return (stat[key]['lv'], key) if key in stat else (0, None)


def match_line(stat, line):
    ks = line['tools'] + line['activities']
    base = dict(line_id=line['line_id'], section=line['section'], text=line['text'], lv_required=line['lv_line'], career_rule=line['career_rule'])
    if line['excluded']: return None
    if line['undecided'] or not line['lv_line'] or not ks: return dict(base, status='판단 불가', my_lv=None, keys=[])
    det = []
    for k in ks:
        lv, src = my_lv(stat, k)
        det.append(dict(key=k, my_lv=lv, via=src if src != k else None, evidence=(stat[src]['evidence'][:1] if src else [])))
    lvs = [d['my_lv'] for d in det]; L = line['lv_line']
    ref = max(lvs) if LINE_MODE == 'any' else min(lvs)
    if ref >= L: status = '기법 충족' if (line['scale'] and L >= 4) else '충족'
    elif max(lvs) > 0: status = '부분'
    else: status = '미충족'
    return dict(base, status=status, my_lv=max(lvs), keys=det)


def match_posting(stat, p):
    lines = [x for x in (match_line(stat, l) for l in p['lines']) if x]
    cnt = {s: sum(1 for x in lines if x['status'] == s) for s in ('충족', '기법 충족', '부분', '미충족', '판단 불가')}
    judged = cnt['충족'] + cnt['기법 충족'] + cnt['부분'] + cnt['미충족']
    need = {}                                                    # 이 공고가 요구하는 키와 최고 요구 LV
    for l in p['lines']:
        if l['lv_line'] and not l['excluded']:
            for k in l['tools'] + l['activities']: need[k] = max(need.get(k, 0), l['lv_line'])
    comp = [dict(key=k, lv_required=v, my_lv=my_lv(stat, k)[0]) for k, v in sorted(need.items(), key=lambda x: (-x[1], x[0]))]
    return dict(posting_id=p['posting_id'], company=p['company'], title=p['title'], position=p['position'], link=p['link'], career=p['career'],
                career_note='경력 조건 있음(판정 안 함)' if any(l['career_rule'] for l in p['lines']) else None,
                summary=dict(cnt, judged=judged, rate=round(cnt['충족'] / judged, 3) if judged else None, rate_with_technique=round((cnt['충족'] + cnt['기법 충족']) / judged, 3) if judged else None),
                competencies=comp, lines=lines)


def match_all(stat_doc, postings_doc):
    res = [match_posting(stat_doc['stat'], p) for p in postings_doc['postings']]
    res.sort(key=lambda r: (-(r['summary']['rate'] or 0), -r['summary']['judged']))
    return dict(person=stat_doc['person'], line_mode=LINE_MODE, n_postings=len(res), postings=res)


if __name__ == '__main__':
    json.dump(match_all(json.load(open(sys.argv[1], encoding='utf-8')), json.load(open(sys.argv[2], encoding='utf-8'))), sys.stdout, ensure_ascii=False, indent=1)
