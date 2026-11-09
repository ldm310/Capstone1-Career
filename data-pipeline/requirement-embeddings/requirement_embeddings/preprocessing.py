import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TAXONOMY = ROOT/'backend/src/main/resources/posting-similarity.properties'


def normalize(value):
    value=unicodedata.normalize('NFKC',value or '')
    value=''.join(c for c in value if not unicodedata.category(c).startswith('C') or c in '\n\t\r')
    return re.sub(r'\s+',' ',value).strip()


class Taxonomy:
    def __init__(self,path=TAXONOMY):
        content=Path(path).read_text(encoding='utf-8').replace('\r\n','\n')
        self.hash=hashlib.sha256(content.encode()).hexdigest()
        rules={}
        for line in content.splitlines():
            match=re.match(r'posting-similarity\.taxonomy\.roles\[(\d+)\]\.(code|pattern)=(.*)',line)
            if match:rules.setdefault(int(match[1]),{})[match[2]]=match[3].replace('\\\\','\\')
        self.rules=[(v['code'],re.compile(v['pattern'],re.I)) for _,v in sorted(rules.items())]

    def role(self,row):
        for value in (row.get('unit_name'),row.get('site_job_category'),row.get('posting_title')):
            value=unicodedata.normalize('NFKC',value or '')
            found=[code for code,pattern in self.rules if code.casefold()==value.strip().casefold() or pattern.search(value)]
            if found:return (found[0],None) if len(found)==1 else (None,'AMBIGUOUS_ROLE')
        return None,'UNKNOWN_ROLE'


EXCLUDED = re.compile(r'학력|학사|석사|박사|대졸|고졸|졸업|전공|학위|성실|책임감|열정|긍정적|태도|인성|커뮤니케이션\s*(?:능력|역량)|원활한\s*(?:소통|커뮤니케이션)|협업\s*(?:능력|역량)|\b(?:bachelor|ph\.?d|degree|attitude)\b|master.s\s+degree',re.I)
PRIVATE = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)|(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)|https?://|(?:성명|담당자|연락처|이메일)\s*[:：]|대학교|고등학교|주식회사|\(주\)')
YEARS = re.compile(r'(?:경력\s*)?\d+(?:\s*[-~]\s*\d+)?\s*년\s*(?:이상|이하|미만|초과)?\s*(?:경력|경험)?|\b\d+(?:\s*[-~]\s*\d+)?\s*\+?\s*years?\s*(?:of\s*)?(?:experience)?\b',re.I)


@dataclass(frozen=True)
class Prepared:
    source: dict
    role: str | None
    text: str | None
    input_hash: str | None
    error: str | None
    taxonomy_hash: str


class CompanyFilter:
    def __init__(self,names):
        names={normalize(re.sub(r'주식회사|\(주\)|㈜|\(유\)','',n)) for n in names}
        names={n for n in names if len(n)>=2}
        self.pattern=re.compile('|'.join(re.escape(n) for n in sorted(names,key=lambda n:(-len(n),n))),re.I) if names else None

    def contains(self,text):
        return bool(self.pattern and self.pattern.search(text))


def prepare(row,taxonomy,company_names=()):
    role,error=taxonomy.role(row)
    def skip(code):return Prepared(row,role,None,None,code,taxonomy.hash)
    if error:return skip(error)
    cap=normalize(row['capability_name']) if row['capability_active'] and row['capability_name']!='기타' else ''
    techs=sorted(set(normalize(t) for t in row['tech_names']),key=lambda s:s.encode('utf-8'))
    if not cap and not techs:return skip('UNCLASSIFIED_NO_ACTIVE_TECH')
    text=normalize(html.unescape(row['item_text']))
    checked=' '.join([cap,*techs,text])
    if re.search(r'</?[A-Za-z][^>]*>',checked):return skip('HTML_RISK')
    if PRIVATE.search(checked):return skip('PRIVACY_RISK')
    if EXCLUDED.search(checked):return skip('EDUCATION_OR_ATTITUDE')
    companies=company_names if isinstance(company_names,CompanyFilter) else CompanyFilter((*company_names,row.get('company_name','')))
    if companies.contains(checked):return skip('COMPANY_NAME_PRESENT')
    text=normalize(YEARS.sub('',text))
    if not text:return skip('EMPTY_AFTER_FILTER')
    def escape(value):return value.replace('\\','\\\\').replace(';','\\;').replace('=','\\=')
    sentence=f"[{role}][{row['category']}] capability={escape(cap)}; tech={','.join(escape(t) for t in techs)}; text={escape(text)}"
    return Prepared(row,role,sentence,hashlib.sha256(sentence.encode('utf-8')).hexdigest(),None,taxonomy.hash)
