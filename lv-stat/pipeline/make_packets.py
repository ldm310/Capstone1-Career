#!/usr/bin/env python3
"""LV3 이상 활동 근거 -> 점검 에이전트 입력(packet). 근거 줄 앞뒤, 파일 경로, 커밋 제목, 내 줄 수만 담음(정답·다른 파일 없음).
Usage: python3 make_packets.py <repos_dir> <rows.json> -> stdout JSON list"""
import json, os, re, subprocess, sys

CLAIM = {
 '캐시 도입': '조회 결과를 저장해 두고 다시 쓰는 캐시를 직접 넣었다(성능 목적). 잠금·멱등 키·요청 제한·세션·인증 코드 저장은 캐시가 아님',
 '메시지 큐': '메시지 브로커나 작업 큐로 비동기 처리를 넣었다',
 'OAuth 연동': 'OAuth2·OIDC로 외부 제공자(구글·카카오 등) 로그인을 연동했거나, OAuth2 인가 서버를 직접 구성했다. 자체 JWT 발급·검증만 하는 것은 아님',
 '결제 연동': '결제 대행사(PG)와 실제로 연동하는 코드를 썼다',
 '모니터링 설정': '지표·추적·오류 수집을 설정했다',
 '쿼리 튜닝': '이미 있던 테이블·쿼리의 성능을 개선했다(나중에 건 인덱스, N+1 해결 등). 테이블을 처음 만들 때 함께 만든 인덱스는 아님. 엔티티의 @Index라도 커밋 제목이 성능·인덱스 개선이면 해당함',
 'CI/CD 구축': '서비스를 서버·클라우드에 배포하거나, 빌드·테스트 후 이미지를 게시하는 자동화 workflow를 만들었다. 문서 사이트 배포는 아님',
 'IaC': '인프라를 코드로 정의했다(Terraform 등)',
 'RAG 구축': '벡터 검색과 LLM 호출을 이어 붙인 검색 증강 기능을 만들었다', '배치 처리': '배치·스케줄 작업을 만들었다', '검색 기능 구축': '검색 엔진으로 검색 기능을 만들었다',
 '동시성 제어': '동시에 들어오는 요청에서 데이터가 어긋나지 않게 잠금·버전·격리 수준으로 제어했다',
 'MSA·서비스 분리': '서비스가 둘 이상인 레포에서 여러 서비스에 코드를 썼고, 서비스 사이 통신(게이트웨이, 브로커, Feign, gRPC) 코드를 썼다. 서비스 수와 내 코드가 있는 서비스 수는 evidence 괄호에 있음', '이벤트 기반 아키텍처': '메시지 브로커로 이벤트를 보내는 쪽과 받는 쪽을 모두 구현했다',
 'Kubernetes 운영 설정': 'Kubernetes에 probe와 자원 제한·오토스케일 같은 운영 설정을 했다', '아키텍처 패턴 적용': '헥사고날·클린 아키텍처·DDD 계층 구조를 실제 코드에 적용했다',
 '장애 격리': '서킷 브레이커 등으로 외부 장애가 번지지 않게 했다', '운영 대응 이력': '배포 뒤에 장애·긴급 수정을 처리한 커밋이 있다',
 '부하 테스트': '부하 테스트 스크립트를 작성했다', '무중단 배포': '서비스를 멈추지 않고 배포하는 구성(blue-green, canary, 롤링)을 만들었다',
 '분산 락·분산 트랜잭션': '여러 서버 사이의 잠금이나 outbox·saga로 정합성을 맞췄다', 'DB 복제·파티셔닝': 'DB 복제·읽기 분리·파티셔닝·샤딩을 구성했다',
}


def git(repo, *a):
    return subprocess.run(['git', '-C', repo, *a], capture_output=True, text=True, errors='replace').stdout


def packet(repos, r, pid, ctx=15):
    repo = os.path.join(repos, r['repo']) if repos else r['_path']; ev = r.get('ev', r.get('where'))
    m = re.match(r'(\S+?):(\d+)', ev); m2 = re.match(r'(\S+) \d+줄', ev)
    path = m.group(1) if m else m2.group(1) if m2 else None
    out = dict(id=pid, repo=r['repo'], judgment=r['key'], lv=r['lv'], claim=CLAIM.get(r['key'], ''), person=r.get('dev', r.get('person')), evidence=ev, path=path)
    if not path: return out
    lines = git(repo, 'show', f'HEAD:{path}').splitlines()
    if m:
        n = int(m.group(2)); a, b = max(0, n - 1 - ctx), min(len(lines), n + ctx)
        out['snippet'] = '\n'.join(f"{'>>' if i + 1 == n else '  '}{i + 1:5} {lines[i][:200]}" for i in range(a, b))
        bl = git(repo, 'blame', '-w', '-M', '-C', '-L', f'{n},{n}', '--line-porcelain', 'HEAD', '--', path)
        s = re.search(r'^summary (.*)$', bl, re.M); out['commit_subject'] = s.group(1)[:200] if s else ''
        more = [x for x in re.findall(r'(\S+?):(\d+)', ev)[1:] if '/' in x[0] or '.' in x[0]]
        if more:                                   # 근거 위치가 둘인 판정(받는 쪽 + 보내는 쪽 등)은 둘째 위치도 보여 줌
            p2, n2 = more[0][0], int(more[0][1]); l2 = git(repo, 'show', f'HEAD:{p2}').splitlines()
            out['path2'] = p2; out['snippet2'] = '\n'.join(f"{'>>' if i + 1 == n2 else '  '}{i + 1:5} {l2[i][:200]}" for i in range(max(0, n2 - 9), min(len(l2), n2 + 8)))
    else:
        out['snippet'] = '\n'.join(f'  {i + 1:5} {t[:200]}' for i, t in enumerate(lines[:40]))
    out['file_lines'] = len(lines)
    return out


def from_bundle(bundle, repo_path):
    """근거 묶음 하나 -> packet 목록 (LV3 이상 활동만. 'DB 설계'처럼 줄 근거가 없는 판정은 점검 대상이 아님)"""
    rows = [dict(e, repo=bundle['meta']['repo'], _path=repo_path) for e in bundle['evidence'] if e['kind'] == 'activity' and e['lv'] >= 3 and e['key'] in CLAIM]
    return [packet(None, r, f'{i:04d}') for i, r in enumerate(rows)]


if __name__ == '__main__':
    if sys.argv[1] == '--bundle':          # python3 make_packets.py --bundle bundle.json <repo 폴더> > packets.json
        json.dump(from_bundle(json.load(open(sys.argv[2], encoding='utf-8')), sys.argv[3]), sys.stdout, ensure_ascii=False, indent=1); sys.exit()
    repos, rows = sys.argv[1], json.load(open(sys.argv[2]))
    rows = rows['rows'] if isinstance(rows, dict) else rows
    sel = [r for r in rows if r['lv'] >= 3 and r['key'] in CLAIM]
    json.dump([packet(repos, r, f'{i:04d}') for i, r in enumerate(sel)], sys.stdout, ensure_ascii=False, indent=1)
