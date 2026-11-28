#!/usr/bin/env python3
"""한 사람의 레포 하나를 끝까지 처리: 근거 묶음 -> 점검 packet -> (점검 에이전트) -> stat -> 공고 매칭.
1단계(에이전트 전):  python3 run_pipeline.py --repo-dir <clone 폴더> --name owner/repo --person <이름> --out out/
                     -> out/bundle.json, out/packets.json 을 만들고 멈춤. packets.json 을 verifier_prompt.md 와 함께 LLM에 보냄
2단계(에이전트 후):  같은 명령에 --agent-output out/agent_output.json 을 붙임 -> out/verdicts.json, out/stat.json, out/match.json
규칙만 쓰려면 --no-verify (LV3 이상 활동을 점검 없이 통과로 봄. 정확도는 HANDOFF.md 표 참고)"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bundle as B, make_packets as MP, to_stat as ST, match as MT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo-dir', required=True); ap.add_argument('--name'); ap.add_argument('--person', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--postings', default=os.path.join(HERE, '..', 'data', 'postings.json')); ap.add_argument('--agent-output'); ap.add_argument('--no-verify', action='store_true')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    dump = lambda name, obj: json.dump(obj, open(os.path.join(a.out, name), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    bp = os.path.join(a.out, 'bundle.json')
    if os.path.exists(bp): bundle = json.load(open(bp, encoding='utf-8'))
    else: bundle = B.make_bundle(a.repo_dir, a.name); dump('bundle.json', bundle)
    if a.person not in bundle['meta']['people']: sys.exit(f"'{a.person}' 이(가) 이 레포의 기여자 목록에 없음: {bundle['meta']['people']}")
    mine = dict(bundle, evidence=[e for e in bundle['evidence'] if e['person'] == a.person])
    packets = MP.from_bundle(mine, a.repo_dir); dump('packets.json', packets)
    verdicts = {}
    if a.agent_output:
        out = {x.get('id'): x for x in json.load(open(a.agent_output, encoding='utf-8')) if isinstance(x, dict)}; vl = []
        for p in packets:
            v = out.get(p['id'], {}); vd = v.get('verdict') if v.get('verdict') in ('pass', 'reject', 'unsure') else 'unsure'
            vl.append(dict(repo=p['repo'], person=p['person'], key=p['judgment'], verdict=vd, reason_code=v.get('reason_code'), reason=v.get('reason', ''))); verdicts[(p['repo'], p['person'], p['judgment'])] = vd
        dump('verdicts.json', vl)
    elif not a.no_verify and packets:
        print(f"점검할 판정 {len(packets)}건 -> {os.path.join(a.out, 'packets.json')}\n점검 에이전트 출력을 받은 뒤 --agent-output 으로 다시 실행하거나, 규칙만 쓰려면 --no-verify"); return
    stat = ST.build_stat([bundle], a.person, verdicts); dump('stat.json', stat)
    res = MT.match_all(stat, json.load(open(a.postings, encoding='utf-8'))); dump('match.json', res)
    top = res['postings'][0]
    print(f"stat 키 {len(stat['stat'])}개, 공고 {res['n_postings']}개 매칭. 가장 잘 맞는 공고: {top['company']} / {top['title'][:30]} ({top['summary']})")


if __name__ == '__main__':
    main()
