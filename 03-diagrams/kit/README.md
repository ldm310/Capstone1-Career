# 다이어그램 키트 사용법 (구성자 B용)

공용 파일이다. `kit/` 안의 파일은 고치지 말 것. 그림마다 필요한 조정은 그 그림 HTML의 `<style>`에서 한다. 키트 버그를 발견하면 보고만 한다.

## 파일
- `diagram.css`: 팔레트·카드·태그·범례·표·막대 스타일 (Pretendard 폰트 포함)
- `connect.js`: `edges([...])`로 카드 사이 직각 화살표를 그리고, 화살표·라벨이 상자를 가리는지 검사
- `render.cjs`: HTML → PNG(2배 해상도) + 겹침·넘침·작은 글씨·폰트 검사 JSON 출력
- `TEMPLATE.html`: 모든 부품의 사용 예 (먼저 읽을 것)

## 렌더링
```bash
node /Users/idongmin/Desktop/capstone1-career/diagram-review-2026-10-27/kit/render.cjs <figN.html> <figN.png>
```
- 출력 JSON의 `problems`가 0이 될 때까지 고친다. 0이 안 되면 남은 항목과 그 이유를 보고한다.
- 출력 JSON은 겹침만 잡는다. 반드시 PNG를 Read로 직접 보고 확인한다.
- 부분 확대: 복사본을 만든 뒤 `sips -c <h> <w> --cropOffset <y> <x> copy.png`로 자른다. PNG 픽셀 = CSS px × 2다.

## HTML 뼈대
- `<link rel="stylesheet" href="file:///Users/idongmin/Desktop/capstone1-career/diagram-review-2026-10-27/kit/diagram.css">`
- `<script src="file:///Users/idongmin/Desktop/capstone1-career/diagram-review-2026-10-27/kit/connect.js"></script>` 뒤에 `edges([...])` 호출
- 구조: `.page` > `.fig-head`(`.badge` "그림 N / 9" + `.section-tag`) > `h1.title` > `p.subtitle` > `.canvas`(높이 지정, 안의 `.card`를 `position:absolute`로 배치) > `.note`(설계 고민) > `.legend`
- 페이지 폭은 1200px로 고정하고, 내용 폭은 1088px(좌우 여백 56px)이다. 세로 길이는 내용에 맞추되 원본과 비슷한 비율(대략 1000~1400px)로 한다.

## 부품
- **카드:** `.card` + `input`(회색 입력) | `output`(초록 굵은 테두리) | `risk`(주황) | `hold`(분홍, 보류·경고) | `ext`(외부, 보라 점선) | `planned`(점선 테두리: 계획 단계) | `example`(예시 패널) | `soft`(연초록 큰 띠), 여백 작게는 `tight`
- **카드 안:** `.tag`(+ `llm`/`rule`/`org`/`out`/`risk`/`hold`/`check`/`ext`/`tool`) → `.card-title`(`.sm` 작게) → `.card-body` → `.ref`("그림 N")
- **단계 번호:** `.head-row` 안에 `.step`(01~04, A) / `.step.b`(B, 파랑) + `.card-title`
- **구현 상태:** `.status.done`(구현됨) / `.status.exp`(실험) / `.status.plan`(계획) / `.status.open`(미정)
- **칩:** `.chips` > `.chip`(`<span class="lv">LV2</span>`), 미확인은 `.chip.dim`
- **표:** `table.mini-table`(강조 행 `tr.hit`, 숫자 칸 `td.num`)
- **막대:** `.bar-row`(라벨 | `.bar > i[style=width:80%]` | 4/5 | 80%), 막힌 단계는 `.bar.warn`
- **묶음:** `.group` + `.group-label`(점선 묶음 상자)
- **설계 고민:** `.note` > `.note-label` + `<div>`(강조는 `<b>`)
- **범례:** `.legend` — 색 상자 `<i class="sw llm|rule|risk|hold|out|tool">`, 선 `<svg class="lg">` (TEMPLATE.html 그대로 복사, 위험 분기 선 #c0782d·아니오 선 #b4502f도 같은 방식)

## edges() 항목
`{from, to, kind, fromSide, toSide, fromAt, toAt, midX, midY, via, label, labelSeg, labelAt, labelDx, labelDy, both, noArrow}`
- **kind:** flow(데이터 흐름, 기본) | loop(재판정·반복, 진초록) | ref(참고·피드백, 점선) | risk(위험 분기, 주황) | no(아니오·보류, 빨강) | llm(파랑)
- **side:** right·left·top·bottom (생략하면 자동)
- **at:** 변 위 위치 0~1, 또는 `"align"`(상대편 점과 일직선으로 맞춤)
- **midX / midY:** 꺾이는 위치(페이지 기준 px)
- **via:** `[{x:...}, {y:...}, {xOf:"id", side:"right", offset:20}, {yOf:"id", side:"bottom", offset:16}]` 순서대로 직각 경유
- **같은 변에서 여러 선이 나가면:** fromAt 0.3 / 0.7처럼 나눈다.
- **라벨:** 기본으로 가장 긴 선분 가운데에 붙는다. labelSeg(선분 번호)·labelAt·labelDx/Dy로 옮긴다.
