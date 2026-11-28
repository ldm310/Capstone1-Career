#!/usr/bin/env python3
"""기준표 CSV -> data/postings.json (공고마다 줄, 줄마다 LV와 역량 키).
Usage: python3 tag_postings.py ../data/lv-criteria-final.csv ../data/postings.json"""
import collections, csv, json, re, sys
import keys


def lvnum(x):
    m = re.match(r'LV\s*(\d)', x or ''); return int(m.group(1)) if m else None


def main(src, dst):
    rows = list(csv.DictReader(open(src, encoding='utf-8-sig')))
    posts = collections.OrderedDict()
    for r in rows:
        p = posts.setdefault(r['공고 id'], dict(posting_id=r['공고 id'], company=r['회사'], title=r['공고 제목'], position=r['자리'], link=r['사람인 링크'], career=r['자리 경력'], lines=[]))
        lv = lvnum(r['기술 LV(줄 기준)']); t = keys.tag_line(r['줄 원문']) if lv else dict(tools=[], activities=[], scale=False)
        p['lines'].append(dict(line_id=r['줄 id'], section=r['구분'], text=r['줄 원문'], lv_line=lv, lv_final=lvnum(r['LV']), excluded=r['기술 LV(줄 기준)'] == '제외',
                               undecided=r['상태'] != '확정', career_rule=r['경력 규칙'] or None, tools=t['tools'], activities=t['activities'], scale=t['scale']))
    out = dict(source=src.split('/')[-1], n_postings=len(posts), n_lines=len(rows), postings=list(posts.values()))
    json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    tech = [l for p in posts.values() for l in p['lines'] if l['lv_line']]
    print(f"공고 {len(posts)}개, 줄 {len(rows)}개, LV 있는 줄 {len(tech)}개, 그중 키가 붙은 줄 {sum(1 for l in tech if l['tools'] or l['activities'])}개")


if __name__ == '__main__':
    main(*sys.argv[1:3])
