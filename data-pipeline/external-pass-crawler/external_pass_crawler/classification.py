import re
import unicodedata

# Canonical role / family. Classification uses ROLE metadata, never essay keyword counts.
ROLE_RULES = (
    ("data_engineer", "data", r"데이터\s*엔지니어|data\s*engineer|데이터\s*플랫폼"),
    ("ml_engineer", "data", r"머신러닝|딥러닝|ML\s*engineer|AI\s*(?:개발|엔지니어|연구)"),
    ("data_scientist", "data", r"데이터\s*(?:사이언|분석)|data\s*(?:scientist|analyst)"),
    ("fullstack", "software", r"풀스택|full[ -]?stack"),
    ("backend", "software", r"백엔드|back[ -]?end|서버\s*(?:개발|엔지니어)|server\s*(?:developer|engineer)"),
    ("frontend", "software", r"프론트엔드|front[ -]?end|웹\s*퍼블리"),
    ("mobile", "software", r"안드로이드|android|iOS|모바일\s*(?:개발|엔지니어)|앱\s*개발"),
    ("embedded", "software", r"임베디드|펌웨어|embedded|firmware"),
    ("qa", "software", r"소프트웨어\s*(?:테스트|품질)|QA\s*(?:엔지니어|개발)|테스트\s*자동화"),
    ("devops", "infrastructure", r"devops|SRE|인프라|클라우드|시스템\s*엔지니어"),
    ("security", "infrastructure", r"정보\s*보안|보안\s*(?:개발|엔지니어|관제)|security\s*engineer"),
    ("software", "software", r"소프트웨어|SW\s*(?:개발|직군|직무)|웹\s*개발|프로그래머|software\s*(?:engineer|developer)"),
)
NON_IT = re.compile(r"마케팅|영업|인사|회계|재무|총무|홍보|금융일반|공정|회로설계|반도체|기계|서비스\s*품질|생산|전략기획", re.I)


def roles(text):
    if text in {role for role, _, _ in ROLE_RULES}:
        return {(role, family) for role, family, _ in ROLE_RULES if role == text}
    # Ambiguous business/engineering roles are deliberately not promoted to IT.
    if NON_IT.search(text):
        return set()
    return {(role, family) for role, family, pattern in ROLE_RULES if re.search(pattern, text, re.I)}


def relation(posting_role, material_role):
    target, source = roles(posting_role), roles(material_role)
    if not source or not target:
        return "EXCLUDED"
    if {r for r, _ in target} & {r for r, _ in source}:
        return "EXACT_ROLE"
    if {f for _, f in target} & {f for _, f in source}:
        return "SAME_JOB_FAMILY"
    return "SAME_IT_DOMAIN"


def canonical_role(text):
    found = roles(text)
    return sorted(r for r, _ in found)[0] if found else None


def company_key(value):
    text = unicodedata.normalize("NFKC", value).casefold()
    text = re.sub(r"주식회사|\(주\)|㈜", "", text)
    return re.sub(r"\s+", "", text)


def same_company(expected, actual, aliases=()):
    return company_key(actual) in {company_key(x) for x in (expected, *aliases)}
