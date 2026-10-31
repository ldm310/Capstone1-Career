"""
② 스킬 추출: 본문 글(글 공고) + PaddleOCR 글자(이미지, 남긴 단락만) -> LLM -> 필수·우대·업무·기타(JSON).

  입력: out/page_filter/sections.json 의 PaddleOCR 단락 판정 중 '남기기' 단락,
        글자는 out/page_filter/paddle_boxes/ 의 줄 상자를 행 단위로 이은 것.
        같은 행에서 칸 사이가 넓으면 ' | ' 로 구분한다(좌우로 나뉜 표의 열을 LLM 이 알아보게).
  LLM : OpenAI Responses API, 구조화 출력(JSON 스키마 strict).
        필수·우대·업무·기타를 개조식 항목(text)으로 정리하고, 항목마다 요건(reqs)을 '능력 + 적힌 기술 + 관계'로 적는다.
          능력(capability): capabilities.json 의 능력 목록에서 고른다(없으면 '기타:이름').
          관계(relation): 예시('등' — 같은 능력의 다른 기술도 인정) / 택1 / 모두 / 능력만(기술 이름 없음).
        사용자 역량과 맞춰 볼 때, '관계형(MySQL 등) DB 경험'이면 Oracle 경험자도 충족으로 판정하기 위한 구조다.
  후처리(capdict.py): 기술 이름을 사전으로 통일(AWs→AWS, K8s→Kubernetes), 상위 기술 연결(EC2→AWS),
        스킬이 아닌 것(LLM 모델 이름 등) 제외, 입력 글자에 없는 이름 제외, 사전에 없는 이름·사전과 다른 능력 배정은 표시.
  결과: out/extract/<모델>/<rec_idx>.json, out/extract/index.html (브라우저에서 바로 채점, 로컬 전용)

실행: py -3.12 extract_skills.py [--models gpt-5.6-terra,gpt-5.6-luna] [--effort low]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import numpy as np
from PIL import Image

from capdict import CapDict
from common import IMG_DIR, OUT_DIR, PAGE_DIR, images_by_posting, load_targets
from html_text import BODY, html_text
from table_layout import table_text

PF = os.path.join(OUT_DIR, "page_filter")
EX = os.path.join(OUT_DIR, "extract")
# 답 길이 상한(생각하는 몫 포함). 8,000 이면 모집 부문이 많은 긴 공고의 답이 중간에 잘렸다(③ 1,494건 중 7건)
MAX_OUTPUT_TOKENS = 16000
PRICES = {"gpt-5.6-terra": (2.00, 12.00), "gpt-5.6-luna": (0.20, 1.20), "gpt-5.6-sol": (4.00, 20.00)}  # USD/1M, 2026-10-02 확인

INSTRUCTIONS = """너는 채용공고를 읽고, 지원자에게 요구하는 것과 하게 될 업무를 필수·우대·업무·기타로 나눠 개조식으로 정리한다.
입력은 공고 본문의 글(웹페이지 글)과 공고 이미지를 OCR로 읽은 글이다(둘 중 하나만 있을 수도 있다).
OCR 글은 오탈자가 있을 수 있고, 같은 높이에 나란한 칸은 ' | '로 이어 붙였다(왼쪽 칸부터).
'■ 머리말' 줄은 표의 왼쪽 칸 머리말이고, 그 아래 줄들이 그 칸의 내용이다(다음 '■' 줄 전까지).
여러 이미지·단락은 빈 줄로 나뉜다. 표의 칸이 섞여 보이면 머리말 줄(예: '모집 구분 | 해당 직무 | 우대 사항')을 보고 어느 열인지 판단한다.

공고 전체를 정리한다
- 입력 맨 윗줄의 '사람인 직무 분류'는 이 공고를 사람인에서 어느 직무로 모았는지 알려 주는 참고 정보다.
  이 분류와 다른 직무라도 건너뛰지 않는다. 공고에 있는 모든 모집부문을 하나도 빠뜨리지 않고 정리한다.
- 공고에 여러 직무(모집부문)가 함께 있으면 직무마다 따로 단위를 만든다(예: 기술영업 / 데이터복구 엔지니어 / 응용기술 -> 세 단위).
- 팀 기술 스택이 영역별(Frontend, Backend, Infrastructure, Design 등)로 나뉘어 있으면, 그 영역의 직무 단위가 있으면 그 단위의 기타에,
  없으면 모든 단위의 기타에 영역 이름과 함께 적는다(예: 'Frontend: React, Next.js').
- skipped 는 빈 배열로 둔다(건너뛰는 부문이 없다).
- '사람인 목록 경력 조건'(있을 때)은 사람인 검색 목록에 적힌 이 공고의 경력·고용 조건이다(예: '신입 · 경력 · 정규직').
  단위들의 career 가 이 조건에 있는 신입·경력을 빠뜨리지 않게 한다. 본문에 더 자세한 조건이 있으면 본문을 따른다.
- 입력의 '회사'가 이 공고를 낸 회사다. 이 회사가 직접 모집하는 부문만 단위로 만든다.
  광고·홍보 속 다른 회사의 채용 공고 화면, 수료 후 취업처 예시, '함께 보면 좋은 공고' 같은 추천·링크, 사이트 메뉴 글은 단위로 만들지 않는다.
- it_job: 단위가 IT 직무인지(true/false). IT 직무 = 소프트웨어·웹·앱·임베디드·게임 개발, 데이터·AI, 인프라·클라우드·DevOps·SRE,
  정보보안, 소프트웨어 QA, IT 시스템 운영·기술지원(시스템 엔지니어, 헬프데스크 등), 서버·네트워크·IT 장비 엔지니어.
  IT 직무가 아님 = 영업(기술영업 포함), 마케팅, 기획(비IT), 법무, 회계·재경·세무, 인사·총무, 생산·공정·제조, 품질·인허가(비소프트웨어),
  연구(소프트웨어가 아닌 화학·바이오·화장품 등), 디자인(비개발) 등.
  it_job 이 false 인 단위는 name·career·years 만 적고 required·preferred·duties·other 는 빈 배열로 둔다.

모집 단위(positions)
- 공고의 내용을 모집 단위로 나눠 적는다. 아래 경우는 단위를 따로 만든다.
  0) 모집부문(직무)이 여럿이다 -> 직무마다 한 단위
  1) 신입과 경력의 자격요건·우대사항이 따로 적혀 있다 → 신입 단위, 경력 단위
  2) 같은 직무라도 역할·파트(예: 결제 백엔드, 검색 백엔드 / 데이터 파이프라인, 데이터 플랫폼)별로 요건이 따로 적혀 있다 → 역할마다 한 단위
  여러 경우가 겹치면 직무·역할×경력마다 한 단위.
- 나눠 적을 근거가 없으면 한 단위로 적는다(신입·경력 공통이면 career 는 '신입·경력').
- 모든 단위에 공통으로 적힌 자격요건·우대사항·업무는 각 단위에 모두 넣는다(단위 하나만 봐도 완결되게).
- 단위별로 따로 적힌 목록(예: [경력] 요구사항 / [신입] 요구사항)의 항목은 그 단위에만 넣는다.
  예: 학력 조건이 [신입] 목록에만 있으면 신입 단위에만 둔다. '공통'이라고 적혔거나 단위 구분 없이 적힌 항목만 모든 단위에 넣는다.
- name: 공고에 적힌 모집부문·역할 이름(경력 구분이 있으면 붙인다. 예: '백엔드 개발자 (경력)').
- career: 신입 / 경력 / 신입·경력 / 언급없음. years: 경력 연수만(예: '3년 이상', '5~7년'. '경력' 같은 말은 빼고), 없으면 빈 문자열.
- 각 단위 안에 required(필수)·preferred(우대)·duties(업무)·other(기타)를 아래 규칙대로 적는다.

나눌 곳
- required(필수): 지원 자격·자격요건·필수 조건. 머리말에 '필수'가 없어도 지원 조건을 말하는 항목이면 여기에 둔다.
- preferred(우대): 우대사항, 또는 있으면 좋다·필수는 아니라고 적힌 것.
- duties(업무): 담당업무·주요업무·하는 일. 기술 이름이 없어도 업무 줄은 하나도 빠뜨리지 않고 모두 적는다.
  각 줄의 reqs 에는 그 업무에 필요한 능력을 능력 목록에서 골라 적는다(기술 이름이 없으면 '능력만', 있으면 그 기술도).
  맞는 능력이 없으면 reqs 를 빈 배열로 둔다(업무 줄은 그래도 남긴다).
- other(기타): 위 세 곳이 아닌 곳(팀 기술 스택, 개발 환경, 사용 도구 등) 가운데 기술이 나오는 내용만. 담당업무는 기타가 아니라 업무에 적는다.
- 지원 방법·제출 서류·기재 사항(이력서·포트폴리오 제출, 희망연봉 기재, 지원서 양식, 마감일 등)은 지원자의 역량이 아니므로
  어디에도 넣지 않는다. 단, '포트폴리오가 있는 분만 지원 가능'처럼 지원 자격 자체를 말하는 항목은 필수에 둔다.

각 항목(한 줄)
- text: 개조식 한 줄. '~경험', '~가능자', '~이해', '~우대'처럼 명사형으로 끝낸다. 공고 문장을 읽기 좋게 다듬되
  뜻을 바꾸거나 글에 없는 내용을 보태지 않는다. OCR 오탈자가 문맥상 분명하면 text 에서는 바로잡아 쓴다.
  필수·우대에는 기술 이름이 없는 항목(경력 연수, 학력, 협업·커뮤니케이션 등)도 빠짐없이 적는다.
  기술 이름이 없어도 능력 목록에 맞는 능력이 있으면 그 능력을 '능력만'으로 적는다
  (예: 'Backend 개발 경력 3년 이상' → 백엔드 개발, '로그를 활용한 Debugging 능력' → 디버깅·트러블슈팅).
  맞는 능력이 없을 때만(경력 연수만 적힌 것, 학력, 협업·커뮤니케이션 등) reqs 를 빈 배열로 둔다.
- reqs: 그 줄이 요구하는 능력. 능력 하나마다 한 개씩.
  - capability: 아래 '능력 목록'의 이름 중 가장 알맞은 것을 그대로 고른다. 맞는 것이 없을 때만 '기타'를 고르고 other_name 에 짧은 이름을 쓴다(그 외에는 빈 문자열).
  - techs: 그 능력에 해당해 글에 적힌 구체적인 기술·제품 이름(언어, 프레임워크, DB, 서비스, 도구 이름)만. '음성', '텍스트', '오픈소스' 같은 일반 낱말은 넣지 않는다.
    글에 적힌 표기 그대로(오탈자도 고치지 않는다). 'TCP/UDP'처럼 묶여 있으면 나눈다. 한 줄에 여러 능력이 섞여 있으면 기술마다 알맞은 능력으로 나눈다
    (예: 'Node.js(TypeScript)' → 백엔드 프레임워크: Node.js / 프로그래밍 언어: TypeScript).
  - relation: 적힌 기술을 어떻게 요구하는지.
    예시   — '등', '예:'처럼 예로 든 것. 같은 능력의 다른 기술 경험도 인정된다. 예: '관계형(MySQL, PostgreSQL 등) DB 경험'
    택1    — '또는', '혹은', 'or', '중 하나', '하나 이상'처럼 고르라는 말이 있을 때만. 적힌 것 중 하나면 된다. 예: 'MySQL 또는 MariaDB 기반 개발'
    모두   — '및', '와/과', 빗금(/)으로 묶였거나 특정 기술을 콕 집어 요구한다. 빗금은 고르라는 말이 없으면 모두로 보고,
             개조식 문장에서도 '또는'으로 바꾸지 않는다. 예: 'Java 및 Spring Boot 기반 개발 경력', 'Linux/Unix 지식', 'C/C++ 개발 경험'
    능력만 — 기술 이름 없이 능력만 적혀 있다(techs 는 빈 배열). 예: '클라우드 환경 경험'
- quote: 근거가 된 줄을 글에서 그대로 옮긴다.

스킬이 아닌 것
- LLM 모델·제품 이름(Claude, Gemini, GPT, ChatGPT, Llama 등)이 들어간 것은 techs 에 넣지 않는다(Claude Code, Gemini Pro 포함).
- 자격증, 학위, 직무명은 techs 에 넣지 않는다.

규칙
- 글에 실제로 적힌 내용만 정리한다. 글에 없는 기술이나 조건을 추측하거나 보태지 않는다.
  예: 'AWS 경험'만 적혀 있으면 techs 는 AWS 만이다. EC2·RDS 같은 세부 서비스를 짐작해 붙이지 않는다.
- 같은 기술이 필수와 우대에 모두 적혀 있으면 양쪽 항목에 모두 둔다.
- 필수·우대 구분이 글에서 분명하지 않으면 notes 에 이유를 짧게 적는다. 없으면 빈 문자열.

능력 목록
{CAPABILITIES}"""

CD = CapDict(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "capabilities.json"), encoding="utf-8")))  # 4단계에서 DB 로
# 능력 이름은 사전 목록 + '기타' 중에서만 고르게 강제한다(자유 입력이면 '언어'·'백엔드'처럼 분류 이름을 고르는 일이 생긴다).
REQ = {"type": "object", "additionalProperties": False, "required": ["capability", "other_name", "techs", "relation"],
       "properties": {"capability": {"type": "string", "enum": CD.cap_names() + ["기타"]},
                      "other_name": {"type": "string"},
                      "techs": {"type": "array", "items": {"type": "string"}},
                      "relation": {"type": "string", "enum": ["예시", "택1", "모두", "능력만"]}}}
ITEM = {"type": "object", "additionalProperties": False, "required": ["text", "reqs", "quote"],
        "properties": {"text": {"type": "string"}, "reqs": {"type": "array", "items": REQ}, "quote": {"type": "string"}}}
POSITION = {"type": "object", "additionalProperties": False,
            "required": ["name", "it_job", "career", "years", "required", "preferred", "duties", "other"],
            "properties": {"name": {"type": "string"}, "it_job": {"type": "boolean"},
                           "career": {"type": "string", "enum": ["신입", "경력", "신입·경력", "언급없음"]},
                           "years": {"type": "string"},
                           "required": {"type": "array", "items": ITEM}, "preferred": {"type": "array", "items": ITEM},
                           "duties": {"type": "array", "items": ITEM}, "other": {"type": "array", "items": ITEM}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["positions", "skipped", "notes"],
          "properties": {"positions": {"type": "array", "items": POSITION},
                         "skipped": {"type": "array", "items": {"type": "string"}}, "notes": {"type": "string"}}}
CATS = ("required", "preferred", "duties", "other")


# 작은 모델(luna)용 예시 답안. 실제 샘플 공고가 아니라 지어낸 공고다(시험 공고를 그대로 보여 주면 점수가 부풀려진다).
# 가르치려는 것: ' | '로 섞인 두 열 읽기, 신입/경력 단위 나누기, 공통 요건 복사, 다른 부문 건너뛰기, 일반 낱말은 techs 에 넣지 않기.
EXAMPLES = """

예시 (지어낸 공고)
입력:
사람인 직무 분류: 백엔드 (참고용, 다른 직무 부문도 모두 정리)
회사: (주)예시소프트
사람인 목록 경력 조건: 신입 · 경력 · 정규직

채용 부문 | 서버 개발자 (신입) | 서버 개발자 (경력 3년 이상)
자격요건 | Java 또는 Kotlin 기반 개발 경험 | Spring Boot 기반 REST API 설계·개발 경력
| 자료구조·알고리즘 등 CS 기초 지식 | MySQL 등 관계형 DB 쿼리 튜닝 경험
| 컴퓨터공학 계열 학사 이상 | 백엔드 개발 경력 3년 이상
우대사항 | 개인 프로젝트 배포 경험 | AWS(EC2, RDS) 운영 경험
| AI·데이터 기반 서비스에 대한 관심 | 대용량 트래픽 처리 경험
서버 개발자 공통 자격요건
Git을 활용한 협업 경험
로그를 활용한 디버깅 능력
서버 개발자 담당업무
주문·결제 API 개발 및 운영 (Spring Boot, Redis)
주문 데이터 정합성 점검 및 장애 대응
개발 환경(전 직군 공통)
GitHub, Docker
지원 방법
이력서·포트폴리오 제출, 희망연봉 기재 필수
[프론트엔드 개발자]
경력 2년 이상
React 기반 웹 개발 경험
TypeScript 능숙
[경영지원팀 회계 담당자]
경력 3년 이상
재무제표 작성 및 결산 경험
함께 보면 좋은 공고: OO테크 데이터 엔지니어 채용 바로가기

출력:
{"positions":[
{"name":"서버 개발자 (신입)","it_job":true,"career":"신입","years":"",
 "required":[
  {"text":"Java 또는 Kotlin 기반 개발 경험","reqs":[{"capability":"프로그래밍 언어","other_name":"","techs":["Java","Kotlin"],"relation":"택1"}],"quote":"Java 또는 Kotlin 기반 개발 경험"},
  {"text":"자료구조·알고리즘 등 CS 기초 지식","reqs":[],"quote":"자료구조·알고리즘 등 CS 기초 지식"},
  {"text":"컴퓨터공학 계열 학사 이상","reqs":[],"quote":"컴퓨터공학 계열 학사 이상"},
  {"text":"Git 활용 협업 경험","reqs":[{"capability":"버전 관리","other_name":"","techs":["Git"],"relation":"모두"}],"quote":"Git을 활용한 협업 경험"},
  {"text":"로그를 활용한 디버깅 능력","reqs":[{"capability":"디버깅·트러블슈팅","other_name":"","techs":[],"relation":"능력만"}],"quote":"로그를 활용한 디버깅 능력"}],
 "preferred":[
  {"text":"개인 프로젝트 배포 경험","reqs":[],"quote":"개인 프로젝트 배포 경험"},
  {"text":"AI·데이터 기반 서비스에 대한 관심","reqs":[],"quote":"AI·데이터 기반 서비스에 대한 관심"}],
 "duties":[
  {"text":"주문·결제 API 개발 및 운영","reqs":[{"capability":"백엔드 프레임워크","other_name":"","techs":["Spring Boot"],"relation":"모두"},{"capability":"NoSQL DB","other_name":"","techs":["Redis"],"relation":"모두"}],"quote":"주문·결제 API 개발 및 운영 (Spring Boot, Redis)"},
  {"text":"주문 데이터 정합성 점검 및 장애 대응","reqs":[{"capability":"디버깅·트러블슈팅","other_name":"","techs":[],"relation":"능력만"}],"quote":"주문 데이터 정합성 점검 및 장애 대응"}],
 "other":[
  {"text":"개발 환경: GitHub, Docker","reqs":[{"capability":"버전 관리","other_name":"","techs":["GitHub"],"relation":"모두"},{"capability":"컨테이너","other_name":"","techs":["Docker"],"relation":"모두"}],"quote":"GitHub, Docker"}]},
{"name":"서버 개발자 (경력)","it_job":true,"career":"경력","years":"3년 이상",
 "required":[
  {"text":"Spring Boot 기반 REST API 설계·개발 경력","reqs":[{"capability":"백엔드 프레임워크","other_name":"","techs":["Spring Boot"],"relation":"모두"},{"capability":"API 설계","other_name":"","techs":["REST API"],"relation":"모두"}],"quote":"Spring Boot 기반 REST API 설계·개발 경력"},
  {"text":"MySQL 등 관계형 DB 쿼리 튜닝 경험","reqs":[{"capability":"관계형 DB","other_name":"","techs":["MySQL"],"relation":"예시"},{"capability":"DB 설계·튜닝","other_name":"","techs":[],"relation":"능력만"}],"quote":"MySQL 등 관계형 DB 쿼리 튜닝 경험"},
  {"text":"백엔드 개발 경력 3년 이상","reqs":[{"capability":"백엔드 개발","other_name":"","techs":[],"relation":"능력만"}],"quote":"백엔드 개발 경력 3년 이상"},
  {"text":"Git 활용 협업 경험","reqs":[{"capability":"버전 관리","other_name":"","techs":["Git"],"relation":"모두"}],"quote":"Git을 활용한 협업 경험"},
  {"text":"로그를 활용한 디버깅 능력","reqs":[{"capability":"디버깅·트러블슈팅","other_name":"","techs":[],"relation":"능력만"}],"quote":"로그를 활용한 디버깅 능력"}],
 "preferred":[
  {"text":"AWS(EC2, RDS) 운영 경험","reqs":[{"capability":"클라우드","other_name":"","techs":["AWS","EC2","RDS"],"relation":"모두"}],"quote":"AWS(EC2, RDS) 운영 경험"},
  {"text":"대용량 트래픽 처리 경험","reqs":[],"quote":"대용량 트래픽 처리 경험"}],
 "duties":[
  {"text":"주문·결제 API 개발 및 운영","reqs":[{"capability":"백엔드 프레임워크","other_name":"","techs":["Spring Boot"],"relation":"모두"},{"capability":"NoSQL DB","other_name":"","techs":["Redis"],"relation":"모두"}],"quote":"주문·결제 API 개발 및 운영 (Spring Boot, Redis)"},
  {"text":"주문 데이터 정합성 점검 및 장애 대응","reqs":[{"capability":"디버깅·트러블슈팅","other_name":"","techs":[],"relation":"능력만"}],"quote":"주문 데이터 정합성 점검 및 장애 대응"}],
 "other":[
  {"text":"개발 환경: GitHub, Docker","reqs":[{"capability":"버전 관리","other_name":"","techs":["GitHub"],"relation":"모두"},{"capability":"컨테이너","other_name":"","techs":["Docker"],"relation":"모두"}],"quote":"GitHub, Docker"}]},
{"name":"프론트엔드 개발자","it_job":true,"career":"경력","years":"2년 이상",
 "required":[
  {"text":"경력 2년 이상","reqs":[],"quote":"경력 2년 이상"},
  {"text":"React 기반 웹 개발 경험","reqs":[{"capability":"프론트엔드 프레임워크","other_name":"","techs":["React"],"relation":"모두"}],"quote":"React 기반 웹 개발 경험"},
  {"text":"TypeScript 능숙","reqs":[{"capability":"프로그래밍 언어","other_name":"","techs":["TypeScript"],"relation":"모두"}],"quote":"TypeScript 능숙"}],
 "preferred":[],
 "duties":[],
 "other":[
  {"text":"개발 환경: GitHub, Docker","reqs":[{"capability":"버전 관리","other_name":"","techs":["GitHub"],"relation":"모두"},{"capability":"컨테이너","other_name":"","techs":["Docker"],"relation":"모두"}],"quote":"GitHub, Docker"}]},
{"name":"경영지원팀 회계 담당자","it_job":false,"career":"경력","years":"3년 이상","required":[],"preferred":[],"duties":[],"other":[]}],
"skipped":[],"notes":""}

이 예시에서 볼 점
- 한 줄에 ' | '로 칸이 이어져 있으면 맨 위 머리말 줄(채용 부문 | 신입 | 경력)의 열 순서대로 읽는다. 각 줄의 왼쪽 내용은 신입, 오른쪽 내용은 경력 단위다.
  이렇게 열마다 따로 적힌 단위(신입/경력, A형/B형, 역할별)는 하나도 빠뜨리지 말고 모두 단위로 만든다.
- 담당업무는 업무(duties)에 줄마다 모두 적는다. '주문 데이터 정합성 점검 및 장애 대응'처럼 기술 이름이 없어도 적고, 맞는 능력이 있으면 능력만으로 붙인다.
  '개발 환경'(GitHub, Docker)처럼 업무도 요건도 아닌 곳의 기술은 기타(other)에 적는다.
- '서버 개발자 공통 자격요건'·'서버 개발자 담당업무'는 서버 개발자 신입·경력 단위에만, '전 직군 공통' 개발 환경은 모든 단위에 넣는다.
- 사람인 분류(백엔드)와 다른 부문([프론트엔드 개발자])도 건너뛰지 않고 따로 단위로 만든다. skipped 는 빈 배열.
- [경영지원팀 회계 담당자]는 IT 직무가 아니므로 it_job=false, 이름·경력만 적고 나머지 칸은 비운다.
- '함께 보면 좋은 공고: OO테크 …'는 이 회사가 모집하는 부문이 아니므로 단위로 만들지 않는다.
- 'AI', '데이터', '튜닝', '대용량 트래픽'처럼 구체적인 제품·도구 이름이 아닌 낱말은 techs 에 넣지 않는다(능력만 이거나 reqs 를 빈 배열로).
- '컴퓨터공학 계열 학사 이상'은 신입 열에만 있으므로 신입 단위에만 넣는다(경력 단위에 복사하지 않는다).
- '백엔드 개발 경력 3년 이상', '디버깅 능력'처럼 기술 이름이 없어도 맞는 능력(백엔드 개발, 디버깅·트러블슈팅)이 있으면 능력만으로 적는다.
- '지원 방법'(이력서·포트폴리오 제출, 희망연봉 기재)은 역량이 아니므로 어디에도 넣지 않는다."""


def instructions(examples: bool = False) -> str:
    """능력 목록을 한 줄에 하나씩, 사전의 예시 기술(최대 4개)이나 별칭을 붙여 넣는다. examples=True 면 예시 답안을 덧붙인다."""
    lines = []
    for name, v in CD.capabilities.items():
        ex = [t for t, tv in CD.techs.items() if name in tv.get("caps", []) and not tv.get("parent")][:4]
        hint = ("예: " + ", ".join(ex)) if ex else ("= " + ", ".join(v.get("aliases", [])[:3])) if v.get("aliases") else ""
        lines.append(f"- {name}" + (f" — {hint}" if hint else ""))
    return INSTRUCTIONS.replace("{CAPABILITIES}", "\n".join(lines)) + (EXAMPLES if examples else "")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def rows_text(boxes: list[list]) -> str:
    """줄 상자 -> 행 단위 글자. 세로로 절반 이상 겹치면 같은 행, 칸 사이가 글자 높이의 0.6배를 넘으면 ' | '."""
    boxes = sorted(boxes, key=lambda b: (b[1] + b[3]) / 2)
    rows = []
    for b in boxes:
        if rows:
            r = rows[-1]
            ov = min(b[3], r["y1"]) - max(b[1], r["y0"])
            if ov >= 0.5 * min(b[3] - b[1], r["y1"] - r["y0"]):
                r["items"].append(b)
                r["y0"], r["y1"] = min(r["y0"], b[1]), max(r["y1"], b[3])
                continue
        rows.append({"y0": b[1], "y1": b[3], "items": [b]})
    out = []
    for r in rows:
        items = sorted(r["items"], key=lambda b: b[0])
        line, prev = "", None
        for b in items:
            if prev is not None:
                gap = b[0] - prev[2]
                line += " | " if gap > 0.6 * max(1, min(b[3] - b[1], prev[3] - prev[1])) else " "
            line += b[4].strip()
            prev = b
        out.append(line)
    return "\n".join(out)


TEXT_MIN = 100  # 본문의 보이는 글이 이보다 짧으면(이미지 전용 공고) 글은 쓰지 않는다


def posting_inputs() -> dict[str, dict]:
    """공고마다 LLM 입력 글: 본문의 보이는 글(html_text, 구조 유지) + 이미지 OCR 글(남긴 단락만, 표 정리).
    글 공고는 본문만, 이미지 공고는 OCR 만, 섞인 공고는 둘 다(본문 먼저)."""
    sec_path = os.path.join(PF, "sections.json")
    data = json.load(open(sec_path, encoding="utf-8")) if os.path.exists(sec_path) else {"readers": {"paddle": []}}
    by_rid = {p["rec_idx"]: p for p in data["readers"]["paddle"]}
    out = {}
    for t in load_targets():
        rid = t["rec_idx"]
        if "교육생" in t.get("career", ""):  # 사람인 고용형태 '교육생' = 교육과정 모집(채용 공고 아님) -> 추출하지 않는다
            continue
        parts, kept, dropped = [], 0, 0
        page_path = os.path.join(PAGE_DIR, f"{rid}.html")
        if os.path.exists(page_path):
            body = html_text(open(page_path, encoding="utf-8").read())
            if len(re.sub(r"\s", "", body)) >= TEXT_MIN:
                parts.append(body)
        p = by_rid.get(rid)
        for im in (p["images"] if p else []):
            boxes = json.load(open(os.path.join(PF, "paddle_boxes", im["stem"] + ".json"), encoding="utf-8"))
            with Image.open(os.path.join(IMG_DIR, im["file"])) as src:
                gray = np.asarray(src.convert("L"))  # 표 테두리선 찾기에 쓴다
            for s in im["sections"]:
                if s["decision"] != "남기기":
                    dropped += 1
                    continue
                kept += 1
                inside = [b for b in boxes if s["y0"] <= (b[1] + b[3]) / 2 < s["y1"]]
                # 표('왼쪽 머리말 | 오른쪽 내용', 열 표)는 칸마다 '■ 머리말' + 내용으로, 나머지는 위에서부터 행 단위로 잇는다
                tx = table_text(inside, gray, im["w"]).strip()
                if tx:
                    parts.append(tx)
        if parts:
            out[rid] = {"text": "\n\n".join(parts), "kept": kept, "dropped": dropped, "role": t.get("role", ""), "company": t.get("company", ""),
                        "career": t.get("career", "")}
    return out


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def other_capability(name: str) -> str | None:
    """LLM 이 '기타'로 적은 능력 이름 -> 사전 능력. 능력 이름·별칭이면 그것, 기술 이름이면 그 기술의 첫 능력(예: 'HTML/CSS')."""
    if not name.strip():
        return None
    c = CD.capability(name)
    if c:
        return c
    lk = CD.lookup(name)
    parts = lk["parts"] if lk["kind"] == "multi" else [lk]
    caps = [p["caps"][0] for p in parts if p["kind"] == "tech" and p.get("caps")]
    return caps[0] if caps else None


# IT 표시 안전망: 단위 이름의 낱말로 LLM 의 it_job 표시가 의심스러운지 본다(판정은 바꾸지 않고 표시만).
IT_NAME = re.compile(r"개발|소프트웨어|백엔드|프론트|풀스택|데이터|인공지능|머신러닝|인프라|클라우드|보안|서버|네트워크|웹|앱|"
                     r"software|developer|data|cloud|security|infra|devops|backend|frontend|"
                     r"(?<![A-Za-z])(IT|AI|ML|SW|S/W|SRE|QA)(?![A-Za-z])", re.I)
NONIT_NAME = re.compile(r"마케팅|마케터|법무|변호사|영업|회계|재경|세무|인사|총무|생산|공정|구매|화장품|브랜드|소비자|사업관리|디자이너")


def it_flag(pos: dict) -> str:
    name = pos.get("name", "")
    techs = sum(1 for k in CATS for it in pos.get(k, []) for q in it["reqs"] for e in q["techs"] if e.get("kind") == "tech")
    if pos.get("it_job") is False and (IT_NAME.search(name) or techs >= 3):
        return "비IT로 표시했지만 이름에 IT 낱말이 있거나 IT 기술이 많음"
    if pos.get("it_job") is True and NONIT_NAME.search(name) and not IT_NAME.search(name):
        return "IT로 표시했지만 이름이 비IT 직무 같음"
    return ""


def guard(result: dict, text: str) -> dict:
    """요건(reqs)의 기술 이름을 사전으로 정리한다.
      - 입력 글자에 없는 이름 -> rejected (지어낸 것일 수 있음)
      - 스킬이 아닌 것(LLM 모델 이름, 직무명 등) -> excluded
      - 일반 낱말(AI, Data, 튜닝 등) -> excluded 에 적고 낱말만 뺀다(요건은 남기고, 기술이 안 남으면 관계를 '능력만'으로)
      - 표준 이름으로 통일(AWs→AWS), 상위 기술(EC2→AWS)과 사전상의 능력을 붙인다
      - 사전에 없는 이름, 사전과 다른 능력에 배정된 기술, 목록 밖 능력은 flag 로 표시만 한다
      - 적힌 기술이 모두 제외돼 근거가 사라진 요건은 뺀다
    근거 줄(quote)이 입력에 그대로 없으면 quote_ok=False. 기타 항목은 기술이 하나도 안 남으면 빼고 dropped_items 에 적는다(업무는 남긴다)."""
    t = norm(text)
    rejected, excluded, dropped_items = [], [], []
    for pos in result["positions"]:
        for key in CATS:
            items = []
            for it in pos[key]:
                reqs = []
                for rq in it["reqs"]:
                    cap = CD.capability(rq["capability"])
                    if rq["capability"] == "기타":  # '기타 + 이름'이 사전의 능력 별칭이나 기술이면 그 능력으로 잇는다
                        cap = other_capability(rq.get("other_name") or "")
                    techs, had, dropped, generic = [], len(rq["techs"]), 0, False
                    for raw in rq["techs"]:
                        if not norm(raw) or norm(raw) not in t:
                            rejected.append({"name": raw, "from": key, "position": pos["name"], "text": it["text"]})
                            dropped += 1
                            continue
                        lk = CD.lookup(raw)
                        parts = lk["parts"] if lk["kind"] == "multi" else [lk]
                        kept = 0
                        for p in parts:
                            if p["kind"] in ("exclude", "generic"):
                                excluded.append({"name": raw, "reason": p["reason"], "from": key, "position": pos["name"], "text": it["text"]})
                                if p["kind"] == "generic":  # 일반 낱말: 낱말만 빼고 요건은 남긴다
                                    kept += 1
                                    generic = True
                                continue
                            if p["kind"] == "tech":
                                ent = {"raw": raw, "name": p["name"], "kind": "tech", "caps": p["caps"], "parent": p.get("parent")}
                                if cap and not CD.satisfies(p["caps"], cap):
                                    ent["flag"] = "사전과 다른 능력"
                            elif p["kind"] == "capability":  # 능력 이름이 기술 자리에 온 경우(예: RDBMS) — 구체 기술은 아님
                                ent = {"raw": raw, "name": p["name"], "kind": "capability"}
                            else:
                                ent = {"raw": raw, "name": raw, "kind": "unknown", "flag": "사전에 없음"}
                            kept += 1
                            if all(e["name"] != ent["name"] for e in techs):
                                techs.append(ent)
                        if not kept:
                            dropped += 1
                    if had and dropped == had:
                        continue
                    if generic and not techs:
                        rq["relation"] = "능력만"
                    if rq["capability"] == "기타" and not cap:
                        rq["capability"] = "기타:" + (rq.get("other_name") or "").strip()
                    reqs.append({"capability": cap or rq["capability"], "cap_ok": cap is not None,
                                 "relation": rq["relation"], "techs": techs})
                it["reqs"] = reqs
                it["quote_ok"] = bool(norm(it["quote"])) and norm(it["quote"]) in t
                if key != "other" or any(e["kind"] != "capability" for r in reqs for e in r["techs"]):
                    items.append(it)
                else:  # 기타인데 구체적인 기술 이름이 없는 줄 — 지우되 기록은 남긴다
                    dropped_items.append({"from": key, "position": pos["name"], "text": it["text"]})
            pos[key] = items
    for pos in result["positions"]:
        pos["it_flag"] = it_flag(pos)
    result["rejected"] = rejected
    result["excluded"] = excluded
    result["dropped_items"] = dropped_items
    return result


def count_line(r: dict) -> str:
    items = lambda k: [it for pos in r["positions"] for it in pos.get(k, [])]
    def cnt(k):
        techs = sum(1 for it in items(k) for rq in it["reqs"] for e in rq["techs"] if e["kind"] != "capability")
        return f"{len(items(k)):>2}줄/기술 {techs:>2}"
    flags = sum(1 for k in CATS for it in items(k) for rq in it["reqs"] for e in rq["techs"] if e.get("flag")) + \
        sum(1 for k in CATS for it in items(k) for rq in it["reqs"] if not rq["cap_ok"])
    units = ", ".join(f"{pos['name']}({pos['career']}{' ' + pos['years'] if pos['years'] else ''}){'·비IT' if pos.get('it_job') is False else ''}"
                      f"{'·⚠IT확인' if pos.get('it_flag') else ''}" for pos in r["positions"])
    return (f"단위 {len(r['positions'])}개 [{units}] | 필수 {cnt('required')} | 우대 {cnt('preferred')} | 업무 {cnt('duties')} | 기타 {cnt('other')} | "
            f"근거없음 {len(r['rejected'])} 제외 {len(r.get('excluded', []))} 확인필요 {flags}"
            + (f" | 검사: 다시 부름({r['checks']['used']})" if (r.get("checks") or {}).get("retry") is not None else "")
            + (f" ⚠확인 필요 {len(review_reasons(r))}" if review_reasons(r) else ""))


def review_reasons(r: dict) -> list[dict]:
    """결과의 확인 필요 사유 [{검사, 내용}]. 옛 결과(check_flag: 힌트 문장 목록)도 같은 모양으로 바꿔 돌려준다."""
    if "review_reasons" in r:
        return r["review_reasons"]
    out = []
    for h in r.get("check_flag") or []:
        n = 1 if "경력 조건" in h else 2 if "모집부문" in h else 3
        out.append({"검사": n, "내용": h})
    return out


UNIT_HEAD = re.compile(r"^■ (모집\s*부문|모집\s*분야|직무명|채용\s*분야|모집\s*구분|직무)\s*$")


def unit_checks(r: dict, inp: dict) -> list[dict]:
    """LLM 결과의 모집 단위가 의심스러운지 코드로 본다(문제 없으면 빈 목록).
    반환: [{검사, 내용, 힌트}] — 내용은 DB 의 '확인 필요 사유'로, 힌트는 다시 부를 때 LLM 입력 끝에 붙인다.
      1) 신입·경력을 빠짐없이 담았는가: 사람인 경력 조건(예: '신입 · 경력')에 있는 신입/경력이 단위들의 career 에 없음
      2) 모집 직무를 빠짐없이 담았는가: 입력 표의 '■ 모집부문' 칸(행)이 단위 이름 수보다 많음
      3) IT 직무인데 내용이 비어 있지 않은가: IT 단위인데 필수·우대·업무가 모두 비었음"""
    found, pos = [], r.get("positions", [])
    car = inp.get("career", "")
    want_new = "신입" in car
    want_exp = bool(re.search(r"경력(?!무관)|\d+\s*~\s*\d+\s*년", car))
    cars = {x.get("career") for x in pos}
    if pos and "언급없음" not in cars:
        has_new = bool(cars & {"신입", "신입·경력"})
        has_exp = bool(cars & {"경력", "신입·경력"})
        if (want_new and not has_new) or (want_exp and not has_exp):
            found.append({"검사": 1, "내용": f"경력 조건 '{car}' / 만든 자리 경력: {', '.join(sorted(c for c in cars if c))}",
                          "힌트": f"사람인 목록상 이 공고의 경력 조건은 '{car}'이다. 신입·경력 조건을 빠뜨리지 마라. "
                                  "경력직에만 따로 적힌 조건이 있으면 신입 단위와 경력 단위로 나누고, 하나로 둘 때는 career 를 '신입·경력'으로 적는다."})
    n_head = sum(1 for ln in inp.get("text", "").splitlines() if UNIT_HEAD.match(ln.strip()))
    names = {re.sub(r"\s*\((신입|경력)[^)]*\)\s*$", "", x.get("name", "")) for x in pos}
    if n_head >= 2 and len(names) < n_head:
        found.append({"검사": 2, "내용": f"모집 직무 칸 {n_head}개 / 만든 자리 이름 {len(names)}개",
                      "힌트": f"입력의 표에 모집부문 칸이 {n_head}개 있다. 모집부문마다 따로 단위를 만들어라."})
    for x in pos:
        if x.get("it_job", True) and not any(x.get(k) for k in ("required", "preferred", "duties")):
            found.append({"검사": 3, "내용": f"IT 자리 '{x.get('name')}'의 필수·우대·업무가 비어 있음",
                          "힌트": f"IT 직무 단위 '{x.get('name')}'의 필수·우대·업무가 비어 있다. 그 단위의 자격요건·우대사항·담당업무를 빠뜨리지 말고 적어라."})
    return found


def llm_input(inp: dict, extra: str = "") -> str:
    """LLM 에 보내는 입력 글(머리 3줄 + 공고 글). extra 는 다시 부를 때 끝에 붙이는 힌트."""
    return (f"사람인 직무 분류: {inp['role'] or '(모름)'} (참고용, 다른 직무 부문도 모두 정리)\n회사: {inp.get('company') or '(모름)'}\n"
            + (f"사람인 목록 경력 조건: {inp['career']}\n" if inp.get("career") else "") + f"\n{inp['text']}"
            + (f"\n\n[다시 확인] 앞선 정리에서 아래 문제가 보였다. 고쳐서 다시 정리하라.\n{extra}" if extra else ""))


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def prompt_version(examples: bool) -> str:
    """프롬프트(지시문 + 예시 답안 + JSON 틀)가 바뀌면 바뀌는 짧은 지문."""
    return sha256(instructions(examples) + json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True))[:12]


def call_llm(client, model: str, effort: str, inp: dict, examples: bool, extra: str = ""):
    """LLM 한 번 호출 -> (걸러낸 결과, 표준화 전 답, 입력 토큰, 출력 토큰, 초, 상태). extra 는 입력 끝에 붙이는 다시 확인 힌트."""
    t = time.perf_counter()
    resp = client.responses.create(
        model=model, instructions=instructions(examples),
        input=llm_input(inp, extra),
        max_output_tokens=MAX_OUTPUT_TOKENS,
        reasoning={"effort": effort},
        text={"format": {"type": "json_schema", "name": "skills", "schema": SCHEMA, "strict": True}})
    sec = time.perf_counter() - t
    raw = json.loads(resp.output_text)
    # guard 는 받은 dict 를 고치므로, 표준화 전 답은 복사해 둔다
    return guard(copy.deepcopy(raw), inp["text"]), raw, resp.usage.input_tokens, resp.usage.output_tokens, sec, resp.status


def fail_reason(e: BaseException) -> str:
    """공고 하나의 LLM 추출 실패 원인 이름(Slack 알림용 — 공고 내용은 넣지 않음).
    연결 끊김·사용 한도·서버 오류는 OpenAI 클라이언트가 먼저 4번까지 다시 해 본 뒤에 여기로 온다."""
    if isinstance(e, json.JSONDecodeError):
        return "응답 잘림·형식 오류"
    return {"BadRequestError": "잘못된 요청", "RateLimitError": "사용 한도", "APIConnectionError": "연결 오류",
            "APITimeoutError": "시간 초과", "InternalServerError": "OpenAI 서버 오류"}.get(type(e).__name__, type(e).__name__)


def extract_one(client, model: str, effort: str, rid: str, inp: dict, examples: bool, pin: float, pout: float) -> dict:
    """공고 하나: LLM 추출 → 모집 단위 검사 → 의심되면 힌트를 붙여 한 번 더(덜 의심스러운 쪽, 비용은 두 번 다 셈).
    실패하면 예외를 그대로 던진다(run_model 이 그 공고만 건너뜀). 여러 스레드에서 동시에 불린다 — 파일은 쓰지 않는다."""
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    parsed, raw, tin, tout, sec, status = call_llm(client, model, effort, inp, examples)
    first = unit_checks(parsed, inp)
    reason = lambda found: [{"검사": f["검사"], "내용": f["내용"]} for f in found]
    checks = {"first": reason(first), "retry": None, "used": "first"}
    final = first
    if first:
        p2, raw2, i2, o2, s2, st2 = call_llm(client, model, effort, inp, examples,
                                             extra="\n".join("- " + f["힌트"] for f in first))
        second = unit_checks(p2, inp)
        checks["retry"] = reason(second)
        tin, tout, sec = tin + i2, tout + o2, sec + s2
        if len(second) <= len(first):
            parsed, raw, status, checks["used"], final = p2, raw2, st2, "retry", second
    return {"rec_idx": rid, "model": model, "effort": effort, "examples": examples,
            "prompt_version": prompt_version(examples), "dict_version": CD.version.split()[0] if CD.version else "",
            "input_hash": sha256(llm_input(inp)), "run_at": run_at, "seconds": round(sec, 2),
            "input_tokens": tin, "output_tokens": tout, "cost_usd": round(tin / 1e6 * pin + tout / 1e6 * pout, 6),
            "status": status, "checks": checks, "review_reasons": reason(final), "llm_output_raw": raw, **parsed}


def run_model(client, model: str, effort: str, inputs: dict[str, dict], examples: bool = False, tag: str = "",
              max_usd: float | None = None, workers: int = 1) -> dict:
    """examples=True 면 지시문에 예시 답안을 붙인다. 결과 폴더는 out/extract/<model><tag>/ (같은 모델의 다른 설정을 나눠 저장).
    이미 결과 파일이 있는 공고는 비용 없이 건너뛴다.
    workers: 공고 몇 건을 동시에 LLM 에 보낼지(OpenAI 클라이언트는 여러 스레드에서 같이 써도 됨). 결과 파일·집계는 이 스레드에서만.
    max_usd: 새로 부른 LLM 비용 합이 이 값 이상이면 새 공고를 더 보내지 않고, 이미 보낸 것만 받은 뒤 <EX>/_budget.json 을 쓴다.
      동시에 보내므로 상한을 넘는 폭은 이미 보낸 공고(최대 workers-1건)만큼이다."""
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    d = os.path.join(EX, model + tag)
    os.makedirs(d, exist_ok=True)
    pin, pout = PRICES.get(model, (0, 0))
    stats = {"model": model, "effort": effort, "in": 0, "out": 0, "sec": 0.0, "usd": 0.0,
             "stopped": False, "spent_new": 0.0, "left": 0, "failed": [], "fail_reasons": {}, "fail_detail": {}, "done_new": 0}

    def add(rid: str, r: dict) -> None:
        stats["in"] += r["input_tokens"]
        stats["out"] += r["output_tokens"]
        stats["sec"] += r["seconds"]
        print(f"  [{model}] {rid}  {count_line(r)}  {r['seconds']:.1f}s  in {r['input_tokens']} out {r['output_tokens']}", flush=True)

    new = []
    for rid, inp in inputs.items():
        path = os.path.join(d, f"{rid}.json")
        if os.path.exists(path):
            add(rid, json.load(open(path, encoding="utf-8")))
        else:
            new.append((rid, inp))

    queue, running, sent = iter(new), {}, 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        def send_more() -> None:
            nonlocal sent
            while len(running) < max(1, workers) and not stats["stopped"]:
                if max_usd is not None and stats["spent_new"] >= max_usd:
                    stats["stopped"] = True
                    break
                nxt = next(queue, None)
                if nxt is None:
                    break
                running[pool.submit(extract_one, client, model, effort, nxt[0], nxt[1], examples, pin, pout)] = nxt[0]
                sent += 1

        send_more()
        while running:
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for fut in done:
                rid = running.pop(fut)
                try:
                    r = fut.result()
                except Exception as e:  # 공고 하나의 실패(응답 잘림·거절·잘못된 요청)가 실행 전체를 막지 않게 — 결과 없이 넘어간다
                    stats["failed"].append(rid)
                    why = fail_reason(e)
                    stats["fail_reasons"][why] = stats["fail_reasons"].get(why, 0) + 1
                    stats["fail_detail"][rid] = why
                    print(f"  [{model}] {rid}  추출 실패: {type(e).__name__}: {str(e)[:200]}", flush=True)
                    continue
                json.dump(r, open(os.path.join(d, f"{rid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                stats["spent_new"] += r["cost_usd"]
                stats["done_new"] += 1
                add(rid, r)
            send_more()

    if stats["stopped"]:
        stats["left"] = len(new) - sent
        budget = {"stopped": True, "spent": round(stats["spent_new"], 6), "limit": max_usd, "left": stats["left"]}
        json.dump(budget, open(os.path.join(EX, "_budget.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print(f"  [{model}] 비용 상한 ${max_usd:.2f} 도달: ${budget['spent']:.4f} 사용, 남은 공고 {stats['left']}건", flush=True)
    stats["failed"] = [rid for rid, _ in new if rid in set(stats["failed"])]   # 입력 순서대로
    stats["usd"] = stats["in"] / 1e6 * pin + stats["out"] / 1e6 * pout
    if stats["failed"] and not stats["done_new"]:  # 전부 실패(키 오류·연결 끊김 등) → 태스크 실패로 알린다
        raise RuntimeError(f"[{model}] 새로 부른 공고 {len(stats['failed'])}건이 모두 실패")
    return stats


def build_html(inputs: dict, models: list[str], stats: list[dict], out_name: str = "index.html",
               key: str = "extract_grades_v2", export_name: str = "extract_grades.json", title: str = "스킬 추출 채점") -> None:
    """채점 화면. 다른 설정(예: luna 시험)의 화면은 out_name·key·export_name 을 바꿔 채점 기록이 섞이지 않게 한다."""
    titles = {t["rec_idx"]: t for t in load_targets()}
    imgs = images_by_posting()
    data = []
    for rid, inp in inputs.items():
        res = {}
        for m in models:
            p = os.path.join(EX, m, f"{rid}.json")
            if os.path.exists(p):
                res[m] = json.load(open(p, encoding="utf-8"))
        # 원본 공고 본문(받아 둔 페이지의 user_content) — 화면 안에서 사람인에서 보이는 모습 그대로 띄운다(로컬 전용)
        page_path = os.path.join(PAGE_DIR, f"{rid}.html")
        m_body = BODY.search(open(page_path, encoding="utf-8").read()) if os.path.exists(page_path) else None
        data.append({"rec_idx": rid, "company": titles[rid]["company"], "title": titles[rid]["title"],
                     "kept": inp["kept"], "dropped": inp["dropped"], "text": inp["text"], "res": res, "role": inp.get("role", ""),
                     "images": [{"file": i["file"], "size": f"{i['width']}x{i['height']}"} for i in imgs.get(rid, [])],
                     "page": m_body.group(1) if m_body else "",
                     "url": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=list&rec_idx={rid}"})
    blob = json.dumps({"postings": data, "models": models, "stats": stats}, ensure_ascii=False).replace("</", "<\\/")
    page = (PAGE.replace('"extract_grades_v2"', json.dumps(key)).replace("extract_grades.json", export_name)
            .replace("<title>스킬 추출 채점</title>", f"<title>{title}</title>").replace("<h1>스킬 추출 채점</h1>", f"<h1>{title}</h1>"))
    with open(os.path.join(EX, out_name), "w", encoding="utf-8") as f:
        f.write(page.replace("__DATA__", blob))


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>스킬 추출 채점</title>
<style>
:root{--bg:#f6f6f4;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--accent:#2a5bd7;--req:#2a5bd7;--pref:#2f8a3d;--oth:#7a6f5f;--duty:#8a4fbf;--bad:#c03c3c;--hl:#fff1a8;--sel:#e8efff;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--panel:#1f1f1d;--ink:#e9e8e3;--muted:#9a9993;--line:#34332f;--accent:#7ea2ff;--req:#7ea2ff;--pref:#6cc77a;--oth:#b3a690;--duty:#c49be8;--bad:#ef7b7b;--hl:#5c4f12;--sel:#22314f;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Segoe UI","Malgun Gothic",sans-serif}
header{position:sticky;top:0;z-index:3;background:var(--bg);padding:10px 16px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center}
header h1{font-size:16px;margin:0}.small{color:var(--muted);font-size:12px}.layout{display:flex}
nav{width:220px;flex:none;border-right:1px solid var(--line);padding:8px;position:sticky;top:50px;height:calc(100vh - 50px);overflow:auto}
nav button{display:block;width:100%;text-align:left;background:none;border:0;border-radius:6px;padding:6px 8px;color:inherit;font:inherit;cursor:pointer}
nav button.on{background:var(--panel);box-shadow:inset 3px 0 0 var(--accent)}nav small{display:block;color:var(--muted);font-size:12px}
main{flex:1;min-width:0;padding:12px 16px}h2{font-size:17px;margin:0 0 4px}h3{font-size:14px;margin:14px 0 6px}
table{border-collapse:collapse;background:var(--panel)}th,td{border:1px solid var(--line);padding:5px 8px;vertical-align:top}
table.st td,table.st th{text-align:right;font-size:13px}table.st td:first-child,table.st th:first-child{text-align:left}
.wrap{overflow-x:auto}.cols{display:flex;gap:12px;align-items:flex-start}
.side{flex:0 0 42%;position:sticky;top:62px;max-height:calc(100vh - 80px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px}
.side img{width:100%;display:block;margin-bottom:6px}
mark{color:inherit;border-radius:2px;padding:0 1px}mark.h필수{background:#ffe866}mark.h우대{background:#b9f2a8}mark.h업무{background:#e6d4f7}mark.h기타{background:#c9e6ff}mark.h추가{background:#ffc4dd}
@media (prefers-color-scheme:dark){mark.h필수{background:#6b5a00}mark.h우대{background:#2c5a22}mark.h업무{background:#4a2c63}mark.h기타{background:#1f4566}mark.h추가{background:#6b2a46}}.side pre{margin:0;white-space:pre-wrap;word-break:break-word;font:12px/1.5 ui-monospace,Consolas,"Malgun Gothic",monospace}
.tabs button{border:1px solid var(--line);background:var(--bg);color:inherit;border-radius:6px;padding:3px 9px;font:inherit;font-size:12.5px;cursor:pointer;margin-right:4px}.tabs button.on{background:var(--sel);border-color:var(--accent)}
.main{flex:1;min-width:0}table.g{width:100%;font-size:13px}table.g th{background:var(--bg);text-align:left;font-weight:600}
.nm{font-weight:600}.desc{display:block;color:var(--ink)}.q{display:block;color:var(--muted);font-size:11.5px}
.tag{display:inline-block;border-radius:10px;padding:0 7px;font-size:12px;margin:1px 2px 1px 0;color:#fff}.t필수{background:var(--req)}.t우대{background:var(--pref)}.t업무{background:var(--duty)}.t기타{background:var(--oth)}.tnone{color:var(--muted);background:none;padding:0}
.opts{display:flex;flex-wrap:wrap;gap:3px}.opts label{border:1px solid var(--line);border-radius:6px;padding:1px 7px;cursor:pointer;font-size:12.5px;white-space:nowrap;user-select:none}
.cmt{display:block;width:100%;margin-top:4px;padding:3px 7px;border:1px solid var(--line);border-radius:5px;background:var(--panel);color:inherit;font:inherit;font-size:12.5px}
.cmt:not(:placeholder-shown){border-color:var(--accent)}
.opts input{display:none}.opts label.on{background:var(--sel);border-color:var(--accent);font-weight:600}
tr.done td{background:color-mix(in srgb,var(--panel) 92%,var(--accent))}
.ok{color:var(--pref);font-weight:600}.ng{color:var(--bad);font-weight:600}
.add{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0}.add input[type=text]{padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:inherit;min-width:180px}
.add select,.add button,.btn{padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:inherit;font:inherit;cursor:pointer}
.filtered{font-size:12.5px;color:var(--muted)}.filtered b{color:var(--ink)}
.pos{border-top:1px dashed var(--line);margin-top:8px;padding-top:6px}.pos:first-of-type{border-top:0;margin-top:2px}
.posh{font-weight:700;font-size:13.5px;margin-bottom:2px}.tnonit{background:#8a8a85}
tr.poshead td{background:var(--sel);font-weight:700;font-size:13px}
.roleinfo{margin:6px 0 10px;padding:6px 10px;background:var(--panel);border:1px solid var(--line);border-radius:6px;font-size:13px}
.blt{display:grid;grid-template-columns:repeat(var(--n),minmax(260px,1fr));gap:10px}
.bcol{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:13px;min-width:0}
.bcol ul{margin:2px 0 8px;padding-left:18px}.bcol li{margin:2px 0}
.bsec{font-weight:600;margin-top:6px}.bsec.req{color:var(--req)}.bsec.pref{color:var(--pref)}.bsec.duty{color:var(--duty)}.bsec.oth{color:var(--oth)}
.chip{display:inline-block;font-size:11.5px;border-radius:9px;padding:0 6px;margin:1px 2px 1px 0;color:#fff;white-space:nowrap}
.chip.c기술{background:#5f6b7a}.chip.c기술 small{opacity:.8}.req{margin:2px 0 4px 2px;font-size:12.5px}.rel{color:var(--muted);font-size:12px}.warn{color:#c27400;font-weight:700;margin-left:2px;cursor:help}
.chip.c필수{background:var(--req)}.chip.c우대{background:var(--pref)}.chip.c업무{background:var(--duty)}.chip.c기타{background:var(--oth)}
@media (max-width:1000px){.blt{grid-template-columns:1fr}}
textarea{width:100%;height:150px;font:12px ui-monospace,Consolas,monospace;background:var(--panel);color:inherit;border:1px solid var(--line);border-radius:6px;padding:6px}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin:4px 0 10px;max-width:420px}.bar i{display:block;height:100%;background:var(--accent)}
@media (max-width:1000px){.cols{display:block}.side{position:static;max-height:420px;margin-bottom:10px}}
@media (max-width:760px){.layout{display:block}nav{position:static;height:auto;width:auto}}
</style></head><body>
<header><h1>스킬 추출 채점</h1>
<span class="small">스킬마다 <b>실제 분류</b>를 고르면 모델별 점수가 바로 계산됩니다. 두 모델이 다 놓친 스킬은 '빠진 스킬 추가'로 넣으세요. 표시는 이 브라우저에 저장됩니다.</span></header>
<div class="layout"><nav id="nav"></nav><main id="main"></main></div>
<script>
const D = __DATA__;
const KEY = "extract_grades_v2";
const OPTS = ["필수", "우대", "필수+우대", "업무", "기타", "스킬 아님"];
let G = {}; try { G = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
let cur = -1, sideTab = "page";
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const norm = s => String(s).replace(/\s+/g, "").toLowerCase();
const pct = (a, b) => b ? (a / b * 100).toFixed(1) + "% <span class='small'>(" + a + "/" + b + ")</span>" : "-";
function save(){ try { localStorage.setItem(KEY, JSON.stringify(G)); } catch (e) {} }
function gp(rid){ G[rid] = G[rid] || {rows: {}, added: []}; G[rid].notes = G[rid].notes || {}; return G[rid]; }
function relLabel(q){
  // 저장값(예시/택1/모두/능력만)을 뜻이 바로 읽히는 말로 보여 준다.
  const n = q.techs.filter(e => e.kind !== "capability").length;
  if (q.relation === "예시") return "예시 · 비슷한 것도 인정";
  if (q.relation === "택1") return "이 중 하나";
  if (q.relation === "모두") return n > 1 ? "모두 필요" : "이 기술 필요";
  return n ? "기술 지정 없음 · 적힌 건 참고" : "기술 지정 없음";
}
function bulletsHTML(r, model){
  if (!r) return "<div class='bcol'><b>" + esc(model) + "</b><div class='small'>결과 없음</div></div>";
  // 항목마다: 개조식 문장 + 그 아래 '능력 ← (관계) 기술'. ⚠ = 사전에 없음·사전과 다른 능력·목록 밖 능력.
  const tech = e => e.kind === "capability" ? "" : "<span class='chip c기술'" + (e.raw !== e.name ? " title='원문: " + esc(e.raw) + "'" : "") + ">" + esc(e.name) +
      (e.parent ? "<small> ⊂" + esc(e.parent) + "</small>" : "") + "</span>" + (e.flag ? "<span class='warn' title='" + esc(e.flag) + "'>⚠</span>" : "");
  const req = (q, label) => "<div class='req'><span class='chip c" + label + "'>" + esc(q.capability) + "</span>" + (q.cap_ok ? "" : "<span class='warn' title='능력 목록 밖'>⚠</span>") +
      (q.techs.filter(e => e.kind !== "capability").length ? " ← " + q.techs.map(tech).join("") : "") + " <span class='rel'>(" + relLabel(q) + ")</span></div>";
  const sec = (pos, k, label, cls) => "<div class='bsec " + cls + "'>" + label + "</div><ul>" + ((pos[k] || []).length ? pos[k].map(it =>
      "<li>" + esc(it.text) + (it.quote_ok === false ? " <span class='small' title='근거 줄이 입력 글자와 그대로 맞지 않음'>⚠</span>" : "") +
      (it.reqs || []).map(q => req(q, label)).join("") + "</li>").join("") : "<li class='small'>없음</li>") + "</ul>";
  // 모집 단위(신입/경력, 역할별)마다 한 덩어리
  return "<div class='bcol'><b>" + esc(model.replace("gpt-5.6-", "")) + "</b>" + (r.positions || []).map((pos, i) =>
      "<div class='pos'><div class='posh'>모집 단위 " + (i + 1) + ": " + esc(pos.name) + " <span class='small'>· " + esc(pos.career) + (pos.years ? " " + esc(pos.years) : "") + "</span>" +
      (pos.it_job === false ? " <span class='tag tnonit'>비IT</span>" : "") + (pos.it_flag ? " <span class='warn' title='" + esc(pos.it_flag) + "'>⚠ IT 확인</span>" : "") + "</div>" +
      sec(pos, "required", "필수", "req") + sec(pos, "preferred", "우대", "pref") + sec(pos, "duties", "업무", "duty") + sec(pos, "other", "기타", "oth") + "</div>").join("") + "</div>";
}
const posLabel = pos => pos.name + " · " + pos.career + (pos.years ? " " + pos.years : "");
function rowsOf(p){
  const m = new Map();
  D.models.forEach(model => { const r = p.res[model]; if (!r) return;
    // 채점 표의 한 줄 = 모집 단위 × 기술(표준 이름). 기술 없이 능력만 있는 요건은 '〔능력〕이름' 한 줄. 설명 칸에는 항목 문장.
    const add = (pos, key, name, cap, it, c, raw) => {
      const k = norm(pos.name) + "|" + key;
      if (!m.has(k)) m.set(k, {key: k, name, pos: posLabel(pos), desc: it.text, quote: it.quote, by: {}, caps: [], raws: []});
      const row = m.get(k); (row.by[model] = row.by[model] || []).includes(c) || row.by[model].push(c);
      if (cap && !row.caps.includes(cap)) row.caps.push(cap);
      if (raw && !row.raws.includes(raw)) row.raws.push(raw);
    };
    (r.positions || []).forEach(pos => [["required","필수"],["preferred","우대"],["duties","업무"],["other","기타"]].forEach(([k, c]) => (pos[k] || []).forEach(it => (it.reqs || []).forEach(q => {
      const ts = q.techs.filter(e => e.kind !== "capability");
      if (!ts.length) add(pos, norm("능력:" + q.capability), "〔능력〕" + q.capability, q.capability, it, c, null);
      ts.forEach(e => add(pos, norm(e.name), e.name, q.capability, it, c, e.raw));
    }))));
  });
  (G[p.rec_idx] ? G[p.rec_idx].added : []).forEach(a => { const key = norm((a.pos || "").split(" · ")[0]) + "|" + norm(a.name);
    if (!m.has(key)) m.set(key, {key, name: a.name, pos: a.pos || "", desc: "", quote: "", by: {}, added: true}); });
  const order = {필수: 0, 우대: 1, 업무: 2, 기타: 3};
  const rows = [...m.values()];
  const posOrder = [...new Set(rows.map(r => r.pos))];
  return rows.sort((a, b) => {
    if (a.pos !== b.pos) return posOrder.indexOf(a.pos) - posOrder.indexOf(b.pos);
    const fa = Math.min(...Object.values(a.by).flat().map(c => order[c]), 3), fb = Math.min(...Object.values(b.by).flat().map(c => order[c]), 3);
    return fa - fb;
  });
}
const actualSet = a => a === "필수" ? ["필수"] : a === "우대" ? ["우대"] : a === "필수+우대" ? ["필수", "우대"] : [];
function score(model, posts){
  const c = {total: 0, graded: 0, req_tp: 0, req_act: 0, req_pred: 0, pref_tp: 0, pref_act: 0, pref_pred: 0, swap: 0, notskill: 0, etcAsReq: 0, missed: 0};
  posts.forEach(p => { const g = (G[p.rec_idx] || {}).rows || {};
    rowsOf(p).forEach(row => { c.total++; const a = g[row.key]; if (!a) return; c.graded++;
      const A = actualSet(a), M = row.by[model] || [], Mr = M.filter(x => x !== "기타" && x !== "업무");
      [["필수","req"],["우대","pref"]].forEach(([cat, k]) => { const inA = A.includes(cat), inM = M.includes(cat);
        if (inA) c[k + "_act"]++; if (inM) c[k + "_pred"]++; if (inA && inM) c[k + "_tp"]++; });
      if (A.length && Mr.length && !A.some(x => Mr.includes(x))) c.swap++;
      if (A.length && !M.length) c.missed++;
      if (a === "스킬 아님" && M.length) c.notskill++;
      if ((a === "기타" || a === "업무") && Mr.length) c.etcAsReq++;
    }); });
  return c;
}
function scoreTable(posts){
  let h = "<div class='wrap'><table class='st'><tr><th>모델</th><th>필수 재현율</th><th>필수 정밀도</th><th>우대 재현율</th><th>우대 정밀도</th><th>필수↔우대 뒤바뀜</th><th>놓친 요건 스킬</th><th>스킬 아닌데 뽑음</th><th>업무·기타를 필수·우대로</th></tr>";
  D.models.forEach(m => { const c = score(m, posts);
    h += "<tr><td>" + esc(m) + "</td><td>" + pct(c.req_tp, c.req_act) + "</td><td>" + pct(c.req_tp, c.req_pred) + "</td><td>" + pct(c.pref_tp, c.pref_act) +
         "</td><td>" + pct(c.pref_tp, c.pref_pred) + "</td><td>" + c.swap + "</td><td>" + c.missed + "</td><td>" + c.notskill + "</td><td>" + c.etcAsReq + "</td></tr>"; });
  return h + "</table></div><p class='small'>재현율 = 실제 필수(우대) 중 모델이 같은 분류로 뽑은 비율. 정밀도 = 모델이 필수(우대)로 뽑은 것 중 실제로 그 분류인 비율. 채점한 스킬만 셉니다.</p>";
}
function progress(posts){ let t = 0, g = 0; posts.forEach(p => { const gr = (G[p.rec_idx] || {}).rows || {}; rowsOf(p).forEach(r => { t++; if (gr[r.key]) g++; }); }); return [g, t]; }
function nav(){
  $("nav").innerHTML = "";
  const b0 = document.createElement("button"); b0.className = cur < 0 ? "on" : ""; const [g0, t0] = progress(D.postings);
  b0.innerHTML = "전체 점수<small>채점 " + g0 + "/" + t0 + "</small>"; b0.onclick = () => { cur = -1; render(); }; $("nav").appendChild(b0);
  D.postings.forEach((p, i) => { const [g, t] = progress([p]); const b = document.createElement("button"); b.className = i === cur ? "on" : "";
    b.innerHTML = esc(p.company) + "<small>채점 " + g + "/" + t + (g === t && t ? " ✓" : "") + "</small>"; b.onclick = () => { cur = i; render(); window.scrollTo(0, 0); }; $("nav").appendChild(b); });
}
function costTable(){
  let h = "<div class='wrap'><table class='st'><tr><th>모델</th><th>추론</th><th>입력 토큰</th><th>출력 토큰</th><th>공고당 비용</th><th>공고당 시간</th><th>근거 없음으로 뺀 것</th><th>스킬이 아니라 뺀 것</th></tr>";
  D.stats.forEach(s => { let rej = 0, exl = 0; D.postings.forEach(p => { const r = p.res[s.model]; if (r) { rej += r.rejected.length; exl += (r.excluded || []).length; } });
    h += "<tr><td>" + esc(s.model) + "</td><td>" + esc(s.effort) + "</td><td>" + s.in.toLocaleString() + "</td><td>" + s.out.toLocaleString() + "</td><td>$" + (s.usd / D.postings.length).toFixed(4) +
         "</td><td>" + (s.sec / D.postings.length).toFixed(1) + "초</td><td>" + rej + "</td><td>" + exl + "</td></tr>"; });
  return h + "</table></div>";
}
function feedbackRows(){
  // 분류를 고르거나 코멘트를 단 스킬을 한 줄씩 모은다.
  const out = [];
  D.postings.forEach(p => { const g = G[p.rec_idx]; if (!g) return; const notes = g.notes || {};
    rowsOf(p).forEach(r => { const a = g.rows[r.key], c = notes[r.key];
      if (!a && !c) return;
      const by = {}; D.models.forEach(m => by[m] = (r.by[m] || []).join("+") || "안 뽑음");
      out.push({rec_idx: p.rec_idx, company: p.company, skill: r.name, actual: a || "", models: by, comment: c || "", added: !!r.added}); }); });
  return out;
}
function exportText(){
  const out = {grades: G, feedback: feedbackRows(), scores: {}};
  D.models.forEach(m => out.scores[m] = score(m, D.postings));
  return JSON.stringify(out);
}
function commentTable(){
  const fb = feedbackRows().filter(f => f.comment);
  if (!fb.length) return "<p class='small'>아직 코멘트가 없습니다. 공고별 채점 표의 '실제 분류' 칸 아래에 쓰면 여기 모입니다.</p>";
  return "<div class='wrap'><table class='g'><tr><th>공고</th><th>스킬</th><th>실제 분류</th>" + D.models.map(m => "<th>" + esc(m.replace("gpt-5.6-", "")) + "</th>").join("") + "<th>코멘트</th></tr>" +
    fb.map(f => "<tr><td>" + esc(f.company) + "</td><td>" + esc(f.skill) + "</td><td>" + esc(f.actual || "-") + "</td>" + D.models.map(m => "<td>" + esc(f.models[m]) + "</td>").join("") + "<td>" + esc(f.comment) + "</td></tr>").join("") + "</table></div>";
}
function overview(){
  const [g, t] = progress(D.postings);
  return "<h2>전체 점수 (10건)</h2><div class='small'>채점 " + g + "/" + t + "</div><div class='bar'><i style='width:" + (t ? g / t * 100 : 0) + "%'></i></div>" +
    scoreTable(D.postings) + "<h3>코멘트 모아 보기</h3>" + commentTable() + "<h3>비용·시간</h3>" + costTable() +
    "<h3>채점 결과 내보내기</h3><p class='small'>아래 칸 내용을 복사해 Claude에게 붙여 주시거나, 파일로 받으세요. 이 내용으로 truth.tsv(정답)도 만들 수 있습니다.</p>" +
    "<textarea id='exp' readonly></textarea><div style='margin-top:6px'><button class='btn' id='dl'>파일로 받기</button> <button class='btn' id='reset'>채점 모두 지우기</button></div>";
}
function sideTabOf(p){
  // 고른 탭이 이 공고에 없으면 있는 탭으로(글 공고는 원본 공고, 이미지 공고는 원본 이미지)
  if (sideTab === "page" && !p.page) return p.images.length ? "img" : "txt";
  if (sideTab === "img" && !p.images.length) return p.page ? "page" : "txt";
  return sideTab;
}
function sideHTML(p){
  const t = sideTabOf(p);
  const btn = (k, label, ok) => ok ? "<button data-t='" + k + "' class='" + (t === k ? "on" : "") + "'>" + label + "</button>" : "";
  const tabs = "<div class='tabs'>" + btn("page", "원본 공고", !!p.page) + btn("img", "원본 이미지 " + p.images.length + "장", p.images.length > 0) +
    btn("txt", "LLM에 넣은 글자", true) + " <a class='small' href='" + p.url + "' target='_blank' rel='noopener'>사람인에서 열기 ↗</a></div>";
  if (t === "page") return tabs + "<div class='small' style='margin:4px 0'>받아 둔 공고 본문을 사람인에서 보이는 모습 그대로 띄움(이미지는 사람인 서버에서 불러옴)</div>" +
    "<iframe id='origPage' sandbox='allow-popups allow-popups-to-escape-sandbox' style='width:100%;height:calc(100vh - 170px);border:1px solid var(--line);border-radius:6px;background:#fff'></iframe>";
  if (t === "img") return tabs + "<div class='small' style='margin:4px 0'>" + p.images.length + "장 · 세로로 길면 스크롤 · 이미지를 누르면 원본 크기로 열림</div>" + p.images.map(im => "<a href='../../images/" + encodeURIComponent(im.file) + "' target='_blank' title='원본 크기로 열기'><img loading='lazy' src='../../images/" + encodeURIComponent(im.file) + "' alt='" + esc(im.file) + "'></a>").join("");
  const legend = "<div class='small' style='margin:4px 0'><mark class='h필수'>필수</mark> <mark class='h우대'>우대</mark> <mark class='h업무'>업무</mark> <mark class='h기타'>기타</mark> <mark class='h추가'>직접 추가</mark> · 한 모델이라도 필수로 뽑으면 필수 색</div>";
  return tabs + legend + "<pre style='margin-top:6px'>" + highlightSkills(p.text, rowsOf(p)) + "</pre>";
}
function highlightSkills(text, rows){
  // 뽑힌 스킬 이름을 분류 색으로 칠한다. 긴 이름 먼저(Spring Boot > Spring), 영문 이름은 단어 경계에서만(Java ≠ JavaScript).
  const rank = {필수: 0, 우대: 1, 업무: 2, 기타: 3};
  const cat = r => r.added ? "추가" : (Object.values(r.by).flat().sort((a, b) => rank[a] - rank[b])[0] || "기타");
  const byKey = new Map(rows.map(r => [r.key, cat(r)]));
  rows.forEach(r => (r.raws || []).forEach(x => byKey.set(norm(x), byKey.get(r.key))));
  const pats = [...new Set(rows.flatMap(r => [r.name, ...(r.raws || [])]))].filter(n => n && n.trim().length > 0 && !n.startsWith("〔")).sort((a, b) => b.length - a.length).map(n => {
    const body = n.trim().split(/\s+/).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s*");
    return (/^[A-Za-z0-9]/.test(n) ? "(?<![A-Za-z0-9])" : "") + body + (/[A-Za-z0-9]$/.test(n) ? "(?![A-Za-z0-9])" : "");
  });
  if (!pats.length) return esc(text);
  const re = new RegExp(pats.join("|"), "gi");
  let out = "", last = 0, m;
  while ((m = re.exec(text))) {
    if (!m[0]) { re.lastIndex++; continue; }
    out += esc(text.slice(last, m.index)) + "<mark class='h" + (byKey.get(norm(m[0])) || "기타") + "'>" + esc(m[0]) + "</mark>";
    last = m.index + m[0].length;
  }
  return out + esc(text.slice(last));
}
function posting(p){
  const g = gp(p.rec_idx), rows = rowsOf(p);
  let h = "<h2>" + esc(p.company) + " — " + esc(p.title) + "</h2><div class='small'>rec_idx " + esc(p.rec_idx) +
          " · <a href='https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=" + esc(p.rec_idx) + "' target='_blank' rel='noopener'>사람인 공고 ↗</a></div>";
  h += "<div class='roleinfo'>사람인 직무 분류: <b>" + esc(p.role || "(모름)") + "</b>" + D.models.map(m => { const r = p.res[m]; if (!r) return "";
         const units = (r.positions || []).map(posLabel);
         return " · <b>" + esc(m.replace("gpt-5.6-", "")) + "</b> 모집 단위 " + units.length + "개: " + esc(units.join(" / ") || "-") +
                (r.skipped && r.skipped.length ? " · 건너뜀: " + esc(r.skipped.join(", ")) : " · 건너뜀: 없음"); }).join("") + "</div>";
  h += "<div class='cols'><aside class='side' id='side'>" + sideHTML(p) + "</aside><div class='main'>";
  h += "<h3>LLM이 정리한 내용 (개조식)</h3><div class='blt' style='--n:" + D.models.length + "'>" + D.models.map(m => bulletsHTML(p.res[m], m)).join("") + "</div>";
  h += "<h3>이 공고 점수</h3>" + scoreTable([p]);
  h += "<h3>스킬별 채점</h3><div class='wrap'><table class='g'><tr><th style='width:30%'>스킬 · 나온 항목</th>" + D.models.map(m => "<th>" + esc(m.replace("gpt-5.6-", "")) + "</th>").join("") + "<th>실제 분류</th></tr>";
  let lastPos = null;
  rows.forEach(r => { const a = g.rows[r.key];
    if (r.pos !== lastPos) { lastPos = r.pos; h += "<tr class='poshead'><td colspan='" + (D.models.length + 2) + "'>모집 단위: " + esc(r.pos || "(직접 추가)") + "</td></tr>"; }
    h += "<tr class='" + (a ? "done" : "") + "'><td><span class='nm'>" + esc(r.name) + "</span>" + (r.caps && r.caps.length && !r.name.startsWith("〔") ? " <span class='small'>능력: " + esc(r.caps.join(", ")) + "</span>" : "") + (r.added ? " <span class='small'>(직접 추가)</span>" : "") +
         (r.desc ? "<span class='desc'>" + esc(r.desc) + "</span>" : "") + (r.quote ? "<span class='q'>근거: " + esc(r.quote) + "</span>" : "") + "</td>";
    D.models.forEach(m => { const M = r.by[m] || []; let mark = "";
      if (a) {
        // 필수·우대: 모델의 필수·우대 분류가 실제와 똑같아야 맞음 / 기타: 필수·우대로 넣지 않았으면 맞음 / 스킬 아님: 안 뽑았어야 맞음
        const A = actualSet(a), Mr = M.filter(x => x !== "기타" && x !== "업무");
        const right = A.length ? (A.length === Mr.length && A.every(x => Mr.includes(x))) : ((a === "기타" || a === "업무") ? Mr.length === 0 : M.length === 0);
        mark = right ? " <span class='ok'>✓</span>" : " <span class='ng'>✗</span>";
      }
      h += "<td>" + (M.length ? M.map(c => "<span class='tag t" + c + "'>" + c + "</span>").join("") : "<span class='tag tnone'>안 뽑음</span>") + mark + "</td>"; });
    h += "<td><div class='opts' data-key='" + esc(r.key) + "'>" + OPTS.map(o => "<label class='" + (a === o ? "on" : "") + "'><input type='radio' name='o_" + esc(r.key) + "' value='" + o + "'" + (a === o ? " checked" : "") + ">" + o + "</label>").join("") + "</div>" +
         "<input type='text' class='cmt' data-key='" + esc(r.key) + "' placeholder='코멘트 (예: 담당업무에만 나옴, 일반어라 빼야 함)' value='" + esc(g.notes[r.key] || "") + "'></td></tr>"; });
  h += "</table></div>";
  const units = [...new Set(D.models.flatMap(m => (p.res[m] ? p.res[m].positions : []).map(posLabel)))];
  h += "<div class='add'><b>빠진 스킬 추가</b><select id='addPos'>" + units.map(u => "<option>" + esc(u) + "</option>").join("") + "</select>" +
       "<input type='text' id='addName' placeholder='공고 표기 그대로 (예: Spring Boot)'><select id='addCat'>" +
       ["필수", "우대", "필수+우대"].map(o => "<option>" + o + "</option>").join("") + "</select><button id='addBtn'>추가</button></div>";
  const filt = D.models.map(m => { const r = p.res[m]; if (!r) return "";
    const why = xs => (xs || []).map(x => typeof x === "string" ? x : x["검사"] + ") " + x["내용"]).join(" / ");
    const left = r.review_reasons || r.check_flag || [];
    const ck = r.checks && r.checks.first && r.checks.first.length ? " · 단위 검사: " + esc(why(r.checks.first)) +
      (r.checks.retry ? " → 다시 부름(" + (r.checks.used === "retry" ? "다시 부른 결과 사용" : "처음 결과 유지") + ")" + (left.length ? " ⚠ 확인 필요: " + esc(why(left)) : " 해결") : "") : "";
    const rej = r.rejected.map(x => esc(x.name)).join(", "), exl = (r.excluded || []).map(x => esc(x.name) + "(" + esc(x.reason) + ")").join(", ");
    return (rej || exl || r.notes || ck) ? "<div><b>" + esc(m) + "</b>" + ck + (exl ? " · 스킬이 아니라 뺌: " + exl : "") + (rej ? " · 글자에 없어 뺌: " + rej : "") + (r.notes ? " · 메모: " + esc(r.notes) : "") + "</div>" : ""; }).join("");
  if (filt) h += "<h3>걸러진 것·모델 메모</h3><div class='filtered'>" + filt + "</div>";
  return h + "</div></div>";
}
function render(){
  nav();
  $("main").innerHTML = cur < 0 ? overview() : posting(D.postings[cur]);
  if (cur < 0) {
    $("exp").value = exportText();
    $("dl").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([exportText()], {type: "application/json"})); a.download = "extract_grades.json"; a.click(); };
    $("reset").onclick = () => { if ($("reset").dataset.armed) { G = {}; save(); render(); } else { $("reset").dataset.armed = 1; $("reset").textContent = "한 번 더 누르면 지웁니다"; } };
    return;
  }
  const p = D.postings[cur], g = gp(p.rec_idx);
  document.querySelectorAll(".opts").forEach(o => o.querySelectorAll("input").forEach(inp => inp.onchange = () => {
    g.rows[o.dataset.key] = inp.value; save(); const y = window.scrollY; render(); window.scrollTo(0, y); }));
  document.querySelectorAll(".cmt").forEach(i => i.oninput = () => {
    const v = i.value.trim(); if (v) g.notes[i.dataset.key] = i.value; else delete g.notes[i.dataset.key]; save(); });
  document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => { sideTab = b.dataset.t; render(); });
  const fr = $("origPage");
  if (fr) fr.srcdoc = "<!doctype html><meta charset='utf-8'><base href='https://www.saramin.co.kr/' target='_blank'>" +
    "<style>body{margin:10px;font-family:'Malgun Gothic',sans-serif;color:#222;background:#fff}img{max-width:100%;height:auto}table{max-width:100%}</style>" + p.page;
  $("addBtn").onclick = () => { const n = $("addName").value.trim(); if (!n) return;
    const posName = ($("addPos") && $("addPos").value) || ""; const pos = posName.split(" · ")[0];
    const key = norm(pos) + "|" + norm(n);
    if (!g.added.some(a => norm((a.pos || "").split(" · ")[0]) + "|" + norm(a.name) === key)) g.added.push({name: n, pos: posName});
    g.rows[key] = $("addCat").value; save(); render(); };
}
{ const h = /^#(\d+)(t?)$/.exec(location.hash); if (h) { cur = Math.min(D.postings.length - 1, parseInt(h[1], 10)); if (h[2]) sideTab = "txt"; } }
render();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gpt-5.6-terra,gpt-5.6-luna")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--examples", action="store_true", help="프롬프트에 예시 답안을 붙인다(지금 쓰는 설정)")
    ap.add_argument("--tag", default="", help="결과 폴더 이름 뒤에 붙일 말(예: --tag=-ex → out/extract/gpt-5.6-luna-ex/)")
    ap.add_argument("--max-usd", type=float, default=None, help="이번 실행에서 새로 쓸 LLM 비용 상한(달러). 넘으면 멈추고 _budget.json")
    ap.add_argument("--workers", type=int, default=1, help="공고 몇 건을 동시에 LLM 에 보낼지(Airflow 는 8)")
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    inputs = posting_inputs()
    os.makedirs(EX, exist_ok=True)
    with open(os.path.join(EX, "_inputs.json"), "w", encoding="utf-8") as f:
        json.dump(inputs, f, ensure_ascii=False, indent=1)
    for rid, inp in inputs.items():
        print(f"{rid}: 남긴 단락 {inp['kept']}, 뺀 단락 {inp['dropped']}, 글자 {len(norm(inp['text']))}자")
    if not inputs:  # 새 공고가 없는 날: LLM 을 부르지 않고 끝낸다
        json.dump([], open(os.path.join(EX, "_stats.json"), "w", encoding="utf-8"))
        print("추출할 공고가 없습니다.")
        return
    from openai import OpenAI
    client = OpenAI(max_retries=4, timeout=300)
    stats = [run_model(client, m, args.effort, inputs, examples=args.examples, tag=args.tag, max_usd=args.max_usd,
                       workers=args.workers)
             for m in models]
    for s in stats:
        print(f"{s['model']}: 입력 {s['in']} 출력 {s['out']} 토큰, ${s['usd']:.4f} (공고당 ${s['usd'] / len(inputs):.4f}), "
              f"공고당 {s['sec'] / len(inputs):.1f}s")
    json.dump(stats, open(os.path.join(EX, "_stats.json"), "w", encoding="utf-8"), ensure_ascii=False)
    build_html(inputs, [m + args.tag for m in models], stats)
    print("-> out/extract/index.html")


if __name__ == "__main__":
    main()
