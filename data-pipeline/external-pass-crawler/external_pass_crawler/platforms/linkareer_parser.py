import json
import re
from html.parser import HTMLParser
from ..errors import ParseError
from ..models import Candidate, PublicMaterial, SearchPage


class _NextData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.active = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def _state(html):
    parser = _NextData()
    parser.feed(html)
    try:
        state = json.loads("".join(parser.parts))["props"]["pageProps"]["__APOLLO_STATE__"]
        if not isinstance(state, dict):
            raise ValueError()
        return state
    except (KeyError, TypeError, ValueError):
        raise ParseError("Expected public Linkareer SSR data") from None


def _candidate(record):
    if not isinstance(record, dict):
        raise ParseError()
    rid, company, role = record.get("id"), record.get("organizationName"), record.get("role")
    if not re.fullmatch(r"\d+", str(rid)) or not isinstance(company, str) or not company.strip() or not isinstance(role, str) or not role.strip():
        raise ParseError("Missing identity metadata")
    return Candidate(str(rid), company.strip(), role.strip())


def parse_search(html):
    state = _state(html)
    root = state.get("ROOT_QUERY", {})
    pages = [v for k, v in root.items() if k.startswith("coverLetters(") and isinstance(v, dict) and "edges" in v]
    if len(pages) != 1:
        raise ParseError("Search result shape changed")
    page = pages[0]
    if not isinstance(page.get("totalCount"), int) or not isinstance(page.get("edges"), list):
        raise ParseError()
    found = []
    for edge in page["edges"]:
        try:
            node = edge["node"]
            record = state[node["__ref"]] if "__ref" in node else node
        except (KeyError, TypeError):
            raise ParseError() from None
        candidate = _candidate(record)
        if candidate.external_id not in {c.external_id for c in found}:
            found.append(candidate)
    if page["totalCount"] > 0 and not found:
        raise ParseError("Nonempty result has no readable records")
    return SearchPage(tuple(found), page["totalCount"])


def parse_detail(html, external_id):
    state = _state(html)
    candidate = _candidate(state.get("CoverLetter:" + str(external_id)))
    record = state["CoverLetter:" + str(external_id)]
    content = record.get("content")
    if candidate.external_id != str(external_id) or not isinstance(content, str) or not content.strip():
        raise ParseError("Full public detail is unavailable")
    return PublicMaterial(candidate.external_id, candidate.company, candidate.role, content)
