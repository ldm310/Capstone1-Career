"""Build Career's photo-first, one-page resume as editable DOCX and print HTML.

From frontend: python scripts/build-resume-template.py
Then: node scripts/print-resume-template.mjs
"""
from html import escape
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "downloads"
OUT.mkdir(parents=True, exist_ok=True)


def paragraph(text, style="Normal", align=None):
    alignment = f'<w:jc w:val="{align}"/>' if align else ''
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/>{alignment}</w:pPr><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def cell(content, width, shade=None, merge=None):
    props = f'<w:tcW w:w="{width}" w:type="dxa"/><w:vAlign w:val="center"/>'
    if shade:
        props += f'<w:shd w:fill="{shade}"/>'
    if merge:
        props += '<w:vMerge w:val="restart"/>' if merge == 'start' else '<w:vMerge/>'
    return f'<w:tc><w:tcPr>{props}</w:tcPr>{content or "<w:p/>"}</w:tc>'


def table(rows, widths, borders=False, row_height=None):
    edges = ''.join(f'<w:{edge} w:val="single" w:sz="4" w:color="BAC4CB"/>' for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']) if borders else ''.join(f'<w:{edge} w:val="nil"/>' for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV'])
    height = f'<w:trPr><w:trHeight w:val="{row_height}" w:hRule="atLeast"/><w:cantSplit/></w:trPr>' if row_height else ''
    return '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblLayout w:type="fixed"/><w:tblBorders>' + edges + '</w:tblBorders><w:tblCellMar><w:top w:w="70" w:type="dxa"/><w:bottom w:w="70" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>' + ''.join(f'<w:gridCol w:w="{width}"/>' for width in widths) + '</w:tblGrid>' + ''.join('<w:tr>' + height + row + '</w:tr>' for row in rows) + '</w:tbl>'


def heading(ko, en):
    return paragraph(f'{ko}  {en}', 'Heading1')


education = [('학력사항', 'EDUCATION'),
             '[재학 기간]    [학교명] · [전공]',
             '[재학 기간]    [학교명] · [전공]',
             '평균 학점  [학점] / [만점]  ·  [졸업 / 재학]']
licenses = [('자격증', 'LICENSE'),
            '[자격증명]    [취득일]    [발급 기관]',
            '[자격증명]    [취득일]    [발급 기관]',
            '[자격증명]    [취득일]    [발급 기관]']
skills = [('기술·역량', 'SKILLS'),
          '[역량 키워드]    [직접 수행한 작업 / 활용 경험]',
          '[역량 키워드]    [직접 수행한 작업 / 활용 경험]']
activities = [('교육·활동', 'ACTIVITIES'),
              '[기간]    [교육·활동명] · [담당 역할]',
              '[기간]    [교육·활동명] · [담당 역할]']


def word_section(section):
    return heading(*section[0]) + ''.join(paragraph(text, 'Row') for text in section[1:])


identity_rows = []
for index, (label, value) in enumerate([('성명', '[이름]'), ('연락처', '[연락 가능한 번호]'), ('이메일', '[이메일 주소]')]):
    photo = paragraph('사진', 'Photo', 'center') + paragraph('[이곳에 이미지 삽입]', 'Hint', 'center') + paragraph('3 × 4cm 권장', 'Hint', 'center') if index == 0 else ''
    identity_rows.append(cell(photo, 1900, 'F2F4F5', 'start' if index == 0 else 'continue') + cell(paragraph(label, 'Label', 'center'), 1300, 'EDF4F7') + cell(paragraph(value), 6466))

body = paragraph('CAREER                                                      RESUME', 'Brand')
body += table(identity_rows, [1900, 1300, 6466], True, row_height=810)
body += paragraph('지원 직무  [지원 직무]     GitHub / 포트폴리오  [주소]', 'Meta')
body += table([cell(word_section(education), 4643) + cell('', 380) + cell(word_section(licenses), 4643),
               cell(word_section(skills), 4643) + cell('', 380) + cell(word_section(activities), 4643)], [4643, 380, 4643])
body += heading('프로젝트 경험', 'PROJECT EXPERIENCE')
for index in range(1, 3):
    body += paragraph(f'[프로젝트 이름 {index}]  ·  [담당 역할]                         [시작일 ~ 종료일]', 'Project')
    body += paragraph('수행한 작업  [직접 수행한 작업과 해결한 문제]', 'Row')
    body += paragraph('결과·근거  [개선한 결과 / 확인 가능한 코드·문서 주소]', 'Row')
body += heading('경력사항', 'WORK EXPERIENCE')
for _ in range(2):
    body += paragraph('[회사 / 기관명]  ·  [직무]                                  [근무 기간]', 'Project')
    body += paragraph('업무·기여  [담당 업무, 직접 기여한 일과 결과]', 'Row')
body += paragraph('사진 칸에 이미지를 삽입하고, 대괄호를 내 정보로 바꿔 주세요. 작성 후 PDF로 저장해 업로드하세요.', 'Footer')

document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:bottom="850" w:left="1120" w:right="1120"/></w:sectPr></w:body></w:document>'
styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Malgun Gothic" w:hAnsi="Malgun Gothic" w:eastAsia="맑은 고딕"/><w:sz w:val="18"/><w:color w:val="303C44"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="110" w:line="270" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Brand"><w:name w:val="Brand"/><w:pPr><w:spacing w:after="190"/></w:pPr><w:rPr><w:b/><w:sz w:val="20"/><w:color w:val="315E7E"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Label"><w:name w:val="Label"/><w:rPr><w:b/><w:sz w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Photo"><w:name w:val="Photo"/><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:keepNext/><w:spacing w:before="190" w:after="110"/><w:pBdr><w:bottom w:val="single" w:sz="8" w:space="5" w:color="333F47"/></w:pBdr></w:pPr><w:rPr><w:b/><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Project"><w:name w:val="Project"/><w:pPr><w:keepNext/><w:spacing w:before="130" w:after="90"/></w:pPr><w:rPr><w:b/><w:sz w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Row"><w:name w:val="Row"/><w:pPr><w:spacing w:after="90"/><w:pBdr><w:bottom w:val="single" w:sz="3" w:space="5" w:color="DCE1E5"/></w:pBdr></w:pPr><w:rPr><w:sz w:val="17"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Hint"><w:name w:val="Hint"/><w:rPr><w:sz w:val="15"/><w:color w:val="65717A"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Meta"><w:name w:val="Meta"/><w:pPr><w:spacing w:before="140" w:after="70"/></w:pPr><w:rPr><w:sz w:val="17"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="Footer"/><w:pPr><w:spacing w:before="200"/></w:pPr><w:rPr><w:sz w:val="15"/><w:color w:val="65717A"/></w:rPr></w:style>
</w:styles>'''
with ZipFile(OUT / 'career-resume-template.docx', 'w', ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    archive.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('word/_rels/document.xml.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    archive.writestr('word/document.xml', document)
    archive.writestr('word/styles.xml', styles)


def html_section(section):
    ko, en = section[0]
    return f'<section><h2>{ko} <small>{en}</small></h2>' + ''.join(f'<p class="row">{escape(text)}</p>' for text in section[1:]) + '</section>'


html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>Career 이력서 양식</title><style>
@page{size:A4;margin:0}*{box-sizing:border-box}body{margin:0;font-family:"Malgun Gothic",sans-serif;color:#303c44;font-size:9pt}.page{width:210mm;min-height:297mm;padding:14mm 19mm 15mm;position:relative}.brand{display:flex;justify-content:space-between;font-size:10pt;font-weight:700;letter-spacing:2px;color:#315e7e;margin-bottom:6mm}.brand span{font-size:8pt;letter-spacing:2px;color:#65717a}.identity{display:grid;grid-template-columns:33mm minmax(0,1fr);height:43mm;border:1px solid #bac4cb}.photo{display:flex;align-items:center;justify-content:center;flex-direction:column;background:#f2f4f5;border-right:1px solid #bac4cb;gap:3mm}.photo strong{font-size:12pt;font-weight:500}.photo span{font-size:8pt;color:#65717a}.identity table{border-collapse:collapse;width:100%;table-layout:fixed}.identity th{width:23mm;background:#edf4f7;font-size:10pt;font-weight:500;border-right:1px solid #bac4cb}.identity td{padding:3mm 5mm;font-size:10pt}.identity tr+tr>*{border-top:1px solid #bac4cb}.meta{font-size:8.5pt;margin:4mm 0 1mm;line-height:1.8}.columns{display:grid;grid-template-columns:1fr 1fr;column-gap:8mm}h2{font-size:10.5pt;font-weight:700;margin:6mm 0 2mm;padding-bottom:1.8mm;border-bottom:1.5px solid #333f47}h2 small{font-size:6.5pt;font-weight:400;color:#65717a;margin-left:3px}.row{font-size:8pt;line-height:1.7;margin:0;padding:1.9mm 0;border-bottom:1px solid #dce1e5}.project-title{display:flex;justify-content:space-between;gap:8mm;font-size:9pt;line-height:1.8;margin:3mm 0 0}.project-title span{font-size:8pt;color:#65717a}.project-title strong{font-weight:500}.footer{position:absolute;bottom:11mm;left:19mm;right:19mm;border-top:1px solid #dce1e5;padding-top:3mm;color:#65717a;font-size:7pt;line-height:1.8}.footer p{margin:0}.footer .brand-end{display:flex;justify-content:space-between;margin-top:2mm;font-size:7pt;letter-spacing:.4px}
</style><body><main class="page"><div class="brand">CAREER<span>RESUME</span></div>
<header class="identity"><div class="photo"><strong>사진</strong><span>이미지 삽입</span><span>3 × 4cm 권장</span></div><table aria-label="기본 정보"><tr><th>성명</th><td>[이름]</td></tr><tr><th>연락처</th><td>[연락 가능한 번호]</td></tr><tr><th>이메일</th><td>[이메일 주소]</td></tr></table></header>
<p class="meta">지원 직무  [지원 직무]　 │　 GitHub / 포트폴리오  [주소]</p>
'''
html += '<div class="columns">' + ''.join(html_section(section) for section in [education, licenses, skills, activities]) + '</div>'
html += '<section><h2>프로젝트 경험 <small>PROJECT EXPERIENCE</small></h2>'
for index in range(1, 3):
    html += f'<p class="project-title"><strong>[프로젝트 이름 {index}] · [담당 역할]</strong><span>[시작일 ~ 종료일]</span></p><p class="row">수행한 작업　[직접 수행한 작업과 해결한 문제]</p><p class="row">결과·근거　[개선한 결과 / 확인 가능한 코드·문서 주소]</p>'
html += '</section><section><h2>경력사항 <small>WORK EXPERIENCE</small></h2>'
for _ in range(2):
    html += '<p class="project-title"><strong>[회사 / 기관명] · [직무]</strong><span>[근무 기간]</span></p><p class="row">업무·기여　[담당 업무, 직접 기여한 일과 결과]</p>'
html += '</section><footer class="footer"><p>사진 칸에 이미지를 삽입하고, 대괄호를 내 정보로 바꿔 주세요. 작성 후 PDF로 저장해 업로드하세요.</p><div class="brand-end"><span>CAREER · 경험에서 시작하는 커리어</span><span>RESUME / 01</span></div></footer></main></body></html>'
(OUT / 'career-resume-template.html').write_text(html, encoding='utf-8')
print('Created editable photo-first DOCX and one-page print source')
