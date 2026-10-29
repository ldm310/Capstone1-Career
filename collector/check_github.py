"""GitHub 데이터 추출 실행 입구: 동의 확인 → 추출(extract.py) → DB 저장(store.py) → 요약 출력.

분석은 본인 계정이나 동의를 받은 계정만 한다. 처음 보는 계정은 --consent로 동의 기록을 남겨야 수집한다(동의 철회된 계정은 수집하지 않음).
토큰은 GITHUB_TOKEN 환경 변수에서만 읽는다. 없으면 시간당 60회 한도로 돈다.
"""
import argparse
import datetime
import os
from pathlib import Path

import extract
import store

HERE = Path(__file__).resolve().parent


def report(res):
    print(f"\n계정 {res['login']} · 공개 레포 {len(res['repos'])}개 · 신원 이메일 {len(res['identity']['emails'])}개 · 이름 {res['identity']['names']}개")
    for r in res['repos']:
        if r.get('skipped'): print(f"\n■ {r['full']}  → 건너뜀(실패 아님): {r['skipped']}"); continue
        if r.get('error'): print(f"\n■ {r['full']}  → 건너뜀: {r['error']}"); continue
        if 'activity' not in r: print(f"\n■ {r['full']}  → 처리 전에 중단됨"); continue
        heads = ' · '.join(f'{b} {sha[:7]}' for b, sha in r['heads'].items())
        if 'develop_contains_main' in r: heads += ' (develop이 main을 포함)' if r['develop_contains_main'] else ' (main·develop 갈라짐)'
        own = [c for c in r['commits'] if c['kind'] != 'name_only']
        work = [c for c in own if not c['merge']]
        added = sum(c['added'] for c in work)
        share = f", 가장 큰 commit이 본인 추가 줄의 {max(c['added'] for c in work) / added:.0%}" if added else ''
        kinds = [c['kind'] for c in r['commits']]
        source = {'owner': '소유', 'member': '멤버(collaborator·조직)', 'search': 'commit·PR 검색'}.get(r.get('source'), '')
        print(f"\n■ {r['full']}{' (fork)' if r['fork'] else ''} [{source}]  {heads}")
        print(f"  본인 commit  {len(own)} / 전체 {r['reachable']}  (API {kinds.count('api')} · 이메일 {kinds.count('email')}, "
              f"이름만 일치 {kinds.count('name_only')}는 추정이라 제외)  +{added}/-{sum(c['deleted'] for c in work)}줄(생성 파일 제외){share}")
        a = r['activity']
        for sha, e in r['evals'].items():
            line = f"  평가 {'·'.join(e['branches'])} {sha[:7]}  본인 줄 {e['own']} / {e['own'] + e['name_only'] + e['other']} (파일 {e['files']}, 이름만 {e['name_only']})"
            if a.get('skipped'): print(line); continue
            ran = e['actions'] or e['check_runs'] or e['statuses']
            run = (','.join(map(str, e['conclusions'])) or '있음') if ran else '미확인'
            print(f"{line}  · 실행 Actions {e['actions']} · check {e['check_runs']} · status {e['statuses']} → {run}")
        if a.get('skipped'): print('  본인 줄이 없어 실행·활용 기록 조회는 건너뜀'); continue
        print(f"  활용  PR {a['pulls']} (병합 {a['pulls_merged']}, 본인 {a['pulls_own']}) · 이슈 {a['issues']} · 배포 {a['deployments']} · Actions 전체 {a['actions_all']}")
    if res['external_pr_repos']: print(f"\n본인 소유가 아닌 레포(멤버·검색으로 찾음): {', '.join(res['external_pr_repos'])}")
    print(f"\nAPI {res['api_calls']}회 · 남은 한도 {res['rate_remaining']} · 토큰 {'있음' if res['token'] else '없음'}"
          + (f" · 중단: {res['stopped']}" if res['stopped'] else ''))


def main():
    p = argparse.ArgumentParser(description='GitHub 데이터 추출 (흐름 1~2단계) → DB 저장')
    p.add_argument('url', help='https://github.com/<계정> 또는 계정 이름')
    p.add_argument('--max-size-mb', type=int, default=None, help='이보다 큰 레포는 clone하지 않음(기본: 제한 없음. 부분 clone이라 512KB 이상 파일은 받지 않는다)')
    p.add_argument('--cache', type=Path, default=extract.CACHE_DIR)
    p.add_argument('--db', type=Path, default=HERE / 'out' / 'github.sqlite')
    p.add_argument('--refresh-runs', action='store_true', help='다시 추출하지 않고, 최신 실행에서 실행 기록이 있는 commit의 기록만 새로 받음')
    p.add_argument('--consent', help='처음 보는 계정의 동의 기록: 받은 방법·범위(예: "2026-10-29 카톡, 공개 레포 분석에 동의")')
    p.add_argument('--relation', choices=['본인', '지인'], default='지인', help='--consent와 함께: 계정과의 관계')
    p.add_argument('--consent-date', type=datetime.date.fromisoformat, default=datetime.date.today(), help='--consent와 함께: 동의 날짜(YYYY-MM-DD)')
    a = p.parse_args()
    try: login = extract.parse_login(a.url)
    except ValueError as e: p.error(str(e))
    account = store.get_account(a.db, login)
    if account and account['revoked_at']: p.error(f"{login}은 {account['revoked_at']}에 동의를 철회했습니다. 수집하지 않습니다")
    if not account:
        if not a.consent: p.error(f'{login}의 동의 기록이 없습니다. --consent "동의 받은 방법·날짜·범위"를 넣어 주세요(본인 계정이면 --relation 본인)')
        store.add_account(a.db, login, a.relation, a.consent, a.consent_date.isoformat())
        account = store.get_account(a.db, login)
        print(f"동의 기록 저장: {login} · {a.relation} · {a.consent_date} · {a.consent}")
    if account['github_id']:  # 같은 이름이 다른 사람에게 넘어갔으면 이전 동의로 수집하지 않는다(clone 전에 확인)
        user, _, _ = extract.Api(os.environ.get('GITHUB_TOKEN')).get(f'/users/{login}')
        if user['id'] != account['github_id']:
            p.error(f"{login}의 GitHub 사용자 번호가 동의할 때({account['github_id']})와 다릅니다({user['id']}). 다른 사람일 수 있어 수집하지 않습니다")
    if a.refresh_runs:
        api = extract.Api(os.environ.get('GITHUB_TOKEN'))
        n = store.refresh_runs(a.db, login, lambda full, sha: extract.run_records(api, full, sha))
        print(f'실행 기록이 있는 평가 commit {n}개를 새로 받음 · API {api.calls}회 · 남은 한도 {api.remaining}')
        return
    res = extract.extract(login, os.environ.get('GITHUB_TOKEN'), a.cache, max_size_mb=a.max_size_mb)
    run_id = store.save(a.db, res, account['id'])
    report(res)
    print(f"저장: {a.db} (collect_run id {run_id}) · 본인 줄 증거 단위 {len(res['evidence'])}개")


if __name__ == '__main__': main()
