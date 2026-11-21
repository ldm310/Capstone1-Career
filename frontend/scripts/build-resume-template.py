"""Build Career's editable DOCX and print source without third-party packages.

Run from frontend: python scripts/build-resume-template.py
Then: node scripts/print-resume-template.mjs (uses the installed Edge browser).
"""
from html import escape
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "downloads"
OUT.mkdir(parents=True, exist_ok=True)

pages = [
    [
        ("brand", "CAREER / RESUME"),
        ("title", "나의 경험을 담은 이력서"),
        ("hint", "대괄호 안의 내용을 내 정보로 바꾸고, 작성 후 PDF로 저장해 주세요."),
        ("section", "01  기본 정보"),
        ("name", "[이름]  ·  [지원 직무]"),
        ("field", "이메일  [이메일 주소]     연락처  [연락 가능한 번호]"),
        ("field", "GitHub  [공개 저장소 주소]"),
        ("field", "포트폴리오  [프로젝트를 확인할 수 있는 주소 / 선택]"),
        ("section", "02  나를 소개하는 한 문장"),
        ("field", "[어떤 문제를 해결하는 사람인지, 핵심 경험과 함께 소개해 주세요.]"),
        ("section", "03  프로젝트 경험"),
        ("project", "[프로젝트 이름 1]"),
        ("field", "기간  [YYYY.MM ~ YYYY.MM]     역할  [담당 역할 / 기여 범위]"),
        ("field", "문제와 목표  [어떤 문제를 해결하려고 했나요?]"),
        ("field", "내가 한 일  [직접 수행한 작업과 선택한 방법을 구체적으로 적어 주세요.]"),
        ("field", "결과와 개선  [변경 전후의 차이, 수치 또는 확인 가능한 결과를 적어 주세요.]"),
        ("field", "확인할 근거  [관련 코드, 문서, 결과물 주소]"),
        ("project", "[프로젝트 이름 2]"),
        ("field", "기간  [YYYY.MM ~ YYYY.MM]     역할  [담당 역할 / 기여 범위]"),
        ("field", "문제와 목표  [어떤 문제를 해결하려고 했나요?]"),
        ("field", "내가 한 일  [직접 수행한 작업과 선택한 방법을 구체적으로 적어 주세요.]"),
        ("field", "결과와 개선  [변경 전후의 차이, 수치 또는 확인 가능한 결과를 적어 주세요.]"),
        ("field", "확인할 근거  [관련 코드, 문서, 결과물 주소]"),
    ],
    [
        ("brand", "CAREER / EXPERIENCE"),
        ("title", "경험의 배경과 근거"),
        ("hint", "해당하는 항목만 작성해 주세요. 빈 항목과 안내 문장은 제출 전에 지워도 좋아요."),
        ("section", "04  경력 · 인턴 · 실무 경험"),
        ("project", "[회사 / 기관명]  ·  [직무]"),
        ("field", "기간  [YYYY.MM ~ YYYY.MM]     근무 형태  [정규직 / 인턴 / 기타]"),
        ("field", "주요 업무  [담당 업무와 책임 범위]"),
        ("field", "내가 기여한 일  [팀의 성과와 구분해 내 기여를 적어 주세요.]"),
        ("field", "성과와 근거  [확인 가능한 변화 또는 결과물]"),
        ("section", "05  학력"),
        ("field", "학교 / 전공  [학교명 / 전공]"),
        ("field", "재학 기간 / 상태  [YYYY.MM ~ YYYY.MM / 졸업·재학 등]"),
        ("field", "평균 학점 / 만점  [평균 학점] / [만점]  ·  선택 항목"),
        ("section", "06  자격증 · 교육"),
        ("field", "[자격증 또는 교육명]  ·  [발급 기관]  ·  [취득 / 수료 YYYY.MM]"),
        ("field", "[자격증 또는 교육명]  ·  [발급 기관]  ·  [취득 / 수료 YYYY.MM]"),
        ("section", "07  그 밖의 경험"),
        ("field", "활동명 / 기간  [활동명 / YYYY.MM ~ YYYY.MM]"),
        ("field", "경험과 기여  [직접 한 일, 배운 점, 개선한 내용을 적어 주세요.]"),
        ("field", "확인할 근거  [관련 기록이나 결과물 주소]"),
        ("section", "작성 체크"),
        ("hint", "직접 한 일과 팀이 한 일을 구분했나요? 결과를 확인할 근거가 있나요?"),
        ("hint", "작성하지 않은 대괄호와 안내 문장을 지웠나요? PDF에서 글자를 선택할 수 있나요?"),
        ("hint", "Word에서 파일 → 다른 이름으로 저장 / 내보내기 → PDF를 선택해 주세요."),
    ],
]

style_map = {"brand": "Brand", "title": "Title", "section": "Heading1", "project": "Heading2", "name": "Heading2", "hint": "Hint", "field": "Normal"}
paras = []
for index, blocks in enumerate(pages):
    if index:
        paras.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    for kind, text in blocks:
        paras.append(f'<w:p><w:pPr><w:pStyle w:val="{style_map[kind]}"/></w:pPr><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')

document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + ''.join(paras) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1000" w:bottom="1000" w:left="1150" w:right="1150"/></w:sectPr></w:body></w:document>'
styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Malgun Gothic" w:hAnsi="Malgun Gothic" w:eastAsia="맑은 고딕"/><w:sz w:val="19"/><w:color w:val="334F63"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="125" w:line="290" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Brand"><w:name w:val="Brand"/><w:rPr><w:b/><w:sz w:val="19"/><w:color w:val="315E7E"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:spacing w:before="70" w:after="140"/><w:keepNext/></w:pPr><w:rPr><w:b/><w:sz w:val="38"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="120"/><w:pBdr><w:bottom w:val="single" w:sz="5" w:space="7" w:color="C8D9E7"/></w:pBdr></w:pPr><w:rPr><w:b/><w:sz w:val="23"/><w:color w:val="315E7E"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="100"/></w:pPr><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Hint"><w:name w:val="Hint"/><w:rPr><w:sz w:val="17"/><w:color w:val="536C80"/></w:rPr></w:style>
</w:styles>'''
with ZipFile(OUT / 'career-resume-template.docx', 'w', ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    archive.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('word/_rels/document.xml.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    archive.writestr('word/document.xml', document)
    archive.writestr('word/styles.xml', styles)

html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>Career 이력서 양식</title><style>
@page{size:A4;margin:0}*{box-sizing:border-box}body{margin:0;font-family:"Malgun Gothic",sans-serif;color:#334f63;font-size:10pt}.page{width:210mm;min-height:297mm;padding:17mm 21mm 15mm;break-after:page;position:relative}.page:last-child{break-after:auto}.brand{font-size:10pt;font-weight:700;color:#315e7e;letter-spacing:1.4px;margin:0 0 9mm}.title{font-size:23pt;font-weight:700;letter-spacing:-1px;margin:0 0 4mm}.hint{font-size:8.5pt;line-height:1.8;color:#536c80;margin:0 0 3mm}.section{font-size:11pt;font-weight:700;color:#315e7e;border-bottom:1px solid #c8d9e7;padding-bottom:2.5mm;margin:6mm 0 3.5mm}.name,.project{font-size:11pt;font-weight:700;margin:4mm 0 3mm}.field{font-size:9pt;line-height:1.8;margin:0 0 2.5mm;padding-bottom:1.5mm;border-bottom:1px solid #edf1f6}.footer{position:absolute;bottom:10mm;left:21mm;right:21mm;display:flex;justify-content:space-between;font-size:8pt;color:#536c80}
</style><body>'''
for index, blocks in enumerate(pages):
    html += '<section class="page">'
    html += ''.join(f'<p class="{kind}">{escape(text)}</p>' for kind, text in blocks)
    html += f'<footer class="footer"><span>CAREER · 경험에서 시작하는 커리어</span><span>{index + 1} / 2</span></footer></section>'
html += '</body></html>'
(OUT / 'career-resume-template.html').write_text(html, encoding='utf-8')
print('Created editable DOCX and two-page print source in public/downloads')
