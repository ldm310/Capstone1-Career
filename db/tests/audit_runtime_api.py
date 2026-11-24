"""Read-only HTTP audit. Stores response metadata, never user data or essay bodies."""
import argparse
import datetime as dt
import json
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://localhost:8080')
    parser.add_argument('--posting-id', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'checked_at_kst': dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
              'base_url': args.base_url, 'checks': []}

    def get(path, expected=200):
        started = dt.datetime.now(dt.timezone.utc)
        value = None
        try:
            with urllib.request.urlopen(args.base_url.rstrip('/') + path, timeout=30) as response:
                status = response.status
                value = json.load(response)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            status = None
        report['checks'].append({'path': path, 'status': status, 'expected': expected,
                                 'passed': status == expected,
                                 'seconds': round((dt.datetime.now(dt.timezone.utc)-started).total_seconds(), 3)})
        return value

    get('/api/health')
    listing = get('/api/postings?size=1')
    if listing:
        report['posting_count'] = listing.get('totalElements')
    capabilities = get('/api/capabilities')
    if isinstance(capabilities, list):
        report['capability_count'] = len(capabilities)
    docs = get('/v3/api-docs')
    if docs:
        report['documented_operations'] = [f'{method.upper()} {path}'
            for path, operations in docs.get('paths', {}).items()
            for method in operations if method in ('get', 'post', 'put', 'patch', 'delete')]
    prefix = f'/api/postings/{args.posting_id}'
    detail = get(prefix)
    if detail:
        units = (detail.get('analysis') or {}).get('recruitUnits', [])
        unit = next((u for u in units if u.get('it')), None)
        for endpoint in ('external-pass-materials', 'external-pass-keywords'):
            data = get(prefix + '/' + endpoint)
            if data and endpoint == 'external-pass-materials':
                report['material_sample'] = {'collection': data.get('collection'),
                    'total': data.get('materials', {}).get('totalElements')}
        if unit:
            unit_prefix = prefix + f"/recruit-units/{unit['unitId']}"
            candidates = get(unit_prefix + '/comparison-candidates')
            if candidates:
                report['candidate_response_fields'] = list(candidates)
            state = get(unit_prefix + '/external-pass-collection-status')
            if state:
                report['collection_sample'] = {key: state.get(key) for key in
                    ('candidateSelectionStatus', 'collectionStatus', 'materialCount', 'source')}
        else:
            report['checks'].append({'path': prefix, 'passed': False, 'reason': 'NO_CURRENT_IT_UNIT'})
    get('/api/postings/9223372036854775807', 404)
    get(prefix + '/recruit-units/0/comparison-candidates', 400)
    report['passed'] = all(check['passed'] for check in report['checks'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
