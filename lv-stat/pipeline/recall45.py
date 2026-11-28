#!/usr/bin/env python3
"""LV4~5 놓침 확인: 도구와 별개인 넓은 검색으로 흔적을 찾고, 도구가 못 잡은 (레포, 키)를 보여 줌. Usage: python3 recall45.py <repos_dir>"""
import collections, json, os, re, subprocess, sys
D = sys.argv[1].rstrip('/')
BROAD = {
 '동시성 제어': r'PESSIMISTIC_|@Version|for update|select_for_update|with_for_update|isolation\s*=|isolationLevel',
 '분산 락·분산 트랜잭션': r'redisson|redlock|advisory_lock|setnx|shedlock|distributed.?lock|outbox|saga',
 '이벤트 기반 아키텍처': r'@KafkaListener|@RabbitListener|@SqsListener|@EventPattern|@MessagePattern|KafkaConsumer|consumer\.subscribe',
 'MSA·서비스 분리': r'spring-cloud-starter-gateway|eureka|@FeignClient|grpc|Transport\.(KAFKA|RMQ|TCP|GRPC|NATS)',
 'Kubernetes 운영 설정': r'livenessProbe|readinessProbe|HorizontalPodAutoscaler',
 '아키텍처 패턴 적용': r'hexagonal|헥사고날|/(port|ports|adapter|adapters|usecase|usecases)/|/application/.*/(port|service)|/infrastructure/',
 '장애 격리': r'circuit.?breaker|resilience4j|opossum|pybreaker',
 '부하 테스트': r"from 'k6|from \"k6|locust|jmeter|ngrinder|gatling|artillery",
 '무중단 배포': r'blue.?green|canary|argo.?rollouts|zero.?downtime|무중단|maxUnavailable: 0',
 'DB 복제·파티셔닝': r'replica|sentinel|sharding|PARTITION BY (RANGE|LIST|HASH)|RoutingDataSource',
}
rows = json.load(open(D + '_v4.json'))['rows']
found = collections.defaultdict(set)
for r in rows:
    if r['lv'] >= 4 and r.get('kind') == 'activity': found[r['repo']].add(r['key'])
miss = collections.Counter(); hit = collections.Counter()
for repo in sorted(os.listdir(D)):
    path = os.path.join(D, repo)
    if not os.path.isdir(os.path.join(path, '.git')): continue
    for key, rx in BROAD.items():
        if key == '아키텍처 패턴 적용':
            out = subprocess.run(['git', '-C', path, 'ls-tree', '-r', '--name-only', 'HEAD'], capture_output=True, text=True).stdout
            lines = [l for l in out.splitlines() if re.search(rx, '/' + l, re.I) and not re.search(r'test|node_modules', l, re.I)]
        else:
            out = subprocess.run(['git', '-C', path, 'grep', '-I', '-i', '-n', '-E', rx, 'HEAD', '--', '.', ':!*.md', ':!*lock*', ':!*.json', ':!*.txt', ':!*.svg', ':!*.html'], capture_output=True, text=True, errors='replace').stdout
            lines = [l for l in out.splitlines() if not re.search(r'(^|/)(tests?|__tests__|docs?)/|Test\.|\.test\.|\.spec\.', l.split(':')[1] if ':' in l else l)]
        if key in found[repo]: hit[key] += 1
        elif lines: miss[key] += 1; print(f"X {key} | {repo[:28]} | {len(lines)}줄 | {lines[0][5:160]}")
print('잡음', dict(hit)); print('넓은 검색에만 있음', dict(miss))
