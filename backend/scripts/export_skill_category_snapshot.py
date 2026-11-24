"""Export saved review results, never call an embedding/model API.

python backend/scripts/export_skill_category_snapshot.py path/to/category-browser.html
Only sentence fingerprints and labels are shipped; no vectors or source text.
"""
import collections
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata


def fingerprint(text):
    normalized = re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def main():
    source = Path(sys.argv[1])
    data = json.JSONDecoder().raw_decode(source.read_text(encoding='utf-8').split('const D=', 1)[1])[0]
    names = ['프로그래밍·CS 기초', '백엔드 개발', '데이터베이스', '데이터 엔지니어링·분석',
             '인프라·배포·운영', '코드 품질·테스트', '프론트엔드·앱 개발', 'AI 기술',
             '보안·개인정보보호', '임베디드·장비 제어·연동']
    codes = data['meta']['category_policy']['technical_categories']
    counts = data['meta']['category_counts']
    assert len(codes) == len(names) == 10
    entries = {}
    for row in data['rows']:
        c = row['curation']
        value = {'categoryCodes': c['effective_cats'], 'excluded': c['excluded_from_counts'],
                 'needsReview': bool(row['prediction'].get('needs_review')),
                 'relatedGroups': row.get('other_review', {}).get('groups', [])}
        key = fingerprint(row['text'])
        if key in entries:
            assert entries[key] == value, 'Conflicting normalized sentence classifications'
        entries[key] = value
    groups = data['meta']['other_review_groups']
    catalog = {
        'version': 'flat-10-infra-review-20261119', 'reviewedAt': '2026-11-19',
        'scope': 'SAVED_REVIEW_CORPUS_INCLUDING_HISTORY',
        'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'totalSentences': len(data['rows']), 'countedSentences': data['meta']['counting_review']['counted_rows'],
        'excludedSentences': data['meta']['counting_review']['excluded_rows'],
        'unclassifiedSentences': data['meta']['unclassified_unique_sentences'],
        'otherSentences': counts['OTHER'], 'categoriesOverlap': True, 'levelScoringEnabled': False,
        'categories': [{'code': code, 'name': name, 'sentenceCount': counts[code]}
                       for code, name in zip(codes, names)],
        'auxiliaryTags': [{'code': code, 'name': name, 'sentenceCount': counts[code]}
                          for code, name in [('T', '도구·개발 방식'), ('M', '업종·업무 경험'), ('X', '지원 조건')]],
        'otherGroups': groups['groups'], 'otherGroupsOverlap': True,
        'certificateReferenceSentences': groups['certificate_reference_rows'],
    }
    output = Path(__file__).resolve().parents[1] / 'src/main/resources/skill-categories/reviewed-20261119.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'catalog': catalog, 'entries': entries}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(json.dumps({'fingerprints': len(entries), 'sentences': len(data['rows']), 'bytes': output.stat().st_size}))


if __name__ == '__main__':
    main()
