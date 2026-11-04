import json
import re
from html.parser import HTMLParser

# All persisted strings come from these allowlists, never from source sentences or profiles.
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
    found = [tech for tech, pattern in TECH_PATTERNS.items() if pattern.search(text)]
    observed = set()
    for sentence in re.split(r"[.!?。！？](?:\s+|$)|[\n;]+", text):
        if UNCONFIRMED.search(sentence):
            continue
        if not PROJECT_CONTEXT.search(sentence) and not any(p.search(sentence) for p in TECH_PATTERNS.values()):
            continue
        for name, pattern in SIGNAL_PATTERNS.items():
            if pattern.search(sentence):
                observed.add(name)
    return json.dumps({"technologies": found,
                       "projectSignals": [name for name in SIGNAL_PATTERNS if name in observed]},
                      ensure_ascii=False, separators=(",", ":"))
