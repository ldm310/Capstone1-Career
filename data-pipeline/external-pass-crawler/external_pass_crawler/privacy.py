import json
import re
from html.parser import HTMLParser

# Summary JSON uses these allowlists. Daily prose is stored separately by explicit policy.
TECHS = ("Python", "Java", "Kotlin", "JavaScript", "TypeScript", "C++", "C#", "Go",
         "Spring", "React", "Vue", "Node.js", "Django", "FastAPI", "MySQL", "PostgreSQL",
         "Redis", "MongoDB", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Git",
         "Linux", "Spark", "Kafka", "Airflow", "PyTorch", "TensorFlow", "SQL")
TECH_PATTERNS = {
    tech: re.compile(r"(?<![A-Za-z0-9_])" + re.escape(tech) + r"(?![A-Za-z0-9_])", re.I)
    for tech in TECHS
}

# Require an explicit performed-action predicate; a topic/list/requirement is not evidence.
DONE = (r"\s*(?:(?:을|를)?\s*(?:완료|수행|진행))?"
        r"(?:했습니다|하였습니다|했다|하였다|했어요|했으며|했고|하였으며|하였고|(?:한\s*)?경험이\s*있습니다|한\s*적이\s*있습니다|해\s*본\s*경험이\s*있습니다|해봤습니다|해보았습니다)")
SIGNAL_PATTERNS = {
    "BASIC_USE": r"(?:사용|활용|이용)" + DONE + r"|\bused\b",
    "FEATURE_IMPLEMENTATION": r"(?:구현|개발)" + DONE + r"|\bimplemented\b",
    "INTEGRATION": r"(?:연동|통합|연계)" + DONE + r"|\bintegrated\b",
    "TESTING": r"(?:테스트|검증)(?:[를을]?\s*(?:작성|수행|실행|자동화))?" + DONE + r"|\btested\b",
    "SECURITY_RELIABILITY": (r"(?:예외\s*처리|오류\s*처리|에러\s*처리|인증|인가|접근\s*제어|암호화|보안|재시도|장애\s*복구)"
                             r"[^\n.!?]{0,30}(?:구현|적용|처리|도입|개선)" + DONE),
    "DEPLOYMENT": r"배포" + DONE + r"|\bdeployed\b",
    "OPERATION": r"(?:운영|장애\s*대응|장애\s*분석|장애\s*해결|장애\s*복구)" + DONE + r"|\boperated\b",
    "OPTIMIZATION": (r"(?:성능[^\n.!?]{0,20}(?:개선|최적화)|응답\s*(?:시간|속도)[^\n.!?]{0,20}(?:단축|개선)"
                      r"|쿼리[^\n.!?]{0,20}(?:튜닝|최적화)|지연[^\n.!?]{0,20}(?:단축|개선))" + DONE + r"|\boptimized\b"),
    "ARCHITECTURE": (r"(?:아키텍처|시스템\s*구조|서비스\s*구조|모듈\s*구조|MSA|마이크로서비스)"
                     r"[^\n.!?]{0,30}(?:설계|구성|분리|전환)" + DONE
                     + r"|\bdesigned\s+(?:the\s+)?(?:system\s+)?architecture\b"),
}
SIGNAL_PATTERNS = {name: re.compile(pattern, re.I) for name, pattern in SIGNAL_PATTERNS.items()}
PROJECT_CONTEXT = re.compile(
    r"프로젝트|API|기능|서비스|시스템|서버|소프트웨어|애플리케이션|파이프라인|아키텍처|"
    r"단위\s*테스트|통합\s*테스트|부하\s*테스트|예외\s*처리|"
    r"\b(?:project|api|feature|service|system|server|software|application|pipeline|architecture)\b", re.I)
UNCONFIRMED = re.compile(
    r"않|못했|못하|없(?:습니다|다|었|는)|미(?:구현|배포|수행)|"
    r"계획|예정|목표|관심|학습|공부|배웠|배우|하고\s*싶|해야|필요|"
    r"동료가|팀원이|강사가|튜토리얼|"
    r"\b(?:not|never|plan|planned|planning|intend|want|wish|learn|learned|study|studied|should|would|could)\b", re.I)

# Split only explicit clause boundaries; never assign an action to the nearest technology.
CLAUSE_BOUNDARY = re.compile(r",|，|\b(?:and|while)\b|그리고|반면|또한|(?<=했고)\s+|(?<=했으며)\s+|(?<=하였고)\s+|(?<=하였으며)\s+", re.I)
TECH_LIST = re.compile(r"사용\s*기술|기술\s*(?:스택|목록)|기술\s*[:：]|\b(?:technologies|tech\s*stack|stack)\s*:", re.I)
TECH_EXCLUSION = re.compile(r"없이|제외|대신|\b(?:without|except|rather\s+than)\b", re.I)


def _technologies(text):
    return [tech for tech, pattern in TECH_PATTERNS.items() if pattern.search(text)]


def _signals(text):
    if UNCONFIRMED.search(text):
        return set()
    if not PROJECT_CONTEXT.search(text) and not _technologies(text):
        return set()
    return {name for name, pattern in SIGNAL_PATTERNS.items() if pattern.search(text)}


def _technology_links(sentence, sentence_signals):
    mentioned = set(_technologies(sentence))
    if not mentioned or not sentence_signals or TECH_LIST.search(sentence) or TECH_EXCLUSION.search(sentence):
        return {}
    links = {}
    for clause in CLAUSE_BOUNDARY.split(sentence):
        technologies = _technologies(clause)
        if not technologies:
            continue
        signals = _signals(clause) & sentence_signals
        # Even a single ambiguous/list-only technology clause invalidates sentence-level attribution.
        if len(technologies) != 1 or not signals:
            return {}
        links.setdefault(technologies[0], set()).update(signals)
    return links if set(links) == mentioned else {}


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "blockquote", "q"):
            self.hidden += 1
        elif tag in ("p", "div", "br", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "blockquote", "q") and self.hidden:
            self.hidden -= 1
        elif tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def technical_summary(source):
    """Return only allowlisted technologies and observed action codes as JSON in the existing TEXT column.

    No source sentences, names, contact values, evidence quotes, scores or inferred LV are serialized.
    Sentence-level negation/intent exclusion is deliberately conservative.
    """
    parser = TextOnly()
    parser.feed(source)
    text = " ".join(parser.parts)
    found = _technologies(text)
    observed = set()
    linked = {}
    for sentence in re.split(r"[.!?。！？](?:\s+|$)|[\n;]+", text):
        signals = _signals(sentence)
        observed.update(signals)
        for technology, technology_signals in _technology_links(sentence, signals).items():
            linked.setdefault(technology, set()).update(technology_signals)
    return json.dumps({"technologies": found,
                       "technologySignals": [
                           {"technology": tech, "signals": [name for name in SIGNAL_PATTERNS if name in linked[tech]]}
                           for tech in found if tech in linked],
                       "projectSignals": [name for name in SIGNAL_PATTERNS if name in observed]},
                      ensure_ascii=False, separators=(",", ":"))


def prose_text(source):
    """Retain essay paragraphs for later extraction, without HTML or direct contact details.

    This is not full anonymization. Applicant profile fields are never passed to this function.
    """
    parser = TextOnly()
    parser.feed(source)
    text = "".join(parser.parts)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[이메일 삭제]", text)
    text = re.sub(r"(?<!\d)(?:\+82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)", "[연락처 삭제]", text)
    text = re.sub(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)", "[식별번호 삭제]", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())
