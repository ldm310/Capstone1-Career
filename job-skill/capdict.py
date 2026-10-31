"""
공통 사전 조회: 이름 하나를 넣으면 무엇인지 돌려준다. 사전의 원본은 DB 의 사전 표(capability, tech, tech_capability,
exclude_word)이고, load_dictionary(conn) 가 사용 중인 줄만 읽어 CapDict 에 넘길 모양(dict)으로 만든다.

  kind = tech        구체 기술 (name=표준 이름, caps=속한 능력, parent=상위 기술, 예: EC2 -> AWS)
         capability  능력 이름 자체 (예: RDBMS -> 관계형 DB, NoSQL -> NoSQL DB)
         exclude     스킬이 아님 (LLM 모델 이름, 직무명·약어 등)
         generic     기술 자리에 온 일반 낱말 (AI, Data, 튜닝 등) — 낱말만 빼고 요건은 남긴다
         multi       'Kubernetes(K8s)', 'TCP/UDP' 처럼 여러 개가 붙은 표기 -> parts
         unknown     사전에 없음 (새 기술이거나 OCR 오타 — 사람이 확인)
이름 비교는 대소문자·공백을 무시한다. 공고 쪽과 사용자 쪽이 같은 사전을 써야 맞춰 볼 수 있다.
"""

from __future__ import annotations

import hashlib
import json
import re

OTHER = "기타"  # 사전에 맞는 능력이 없을 때 가리키는 능력(DB 에만 있고 LLM 능력 목록에는 따로 붙인다)
EXCLUDE_KINDS = {"LLM 모델": "llm_models", "기술 아님": "not_skill", "일반 낱말": "generic_words"}  # exclude_word.kind -> 키


def key(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def load_dictionary(conn) -> dict:
    """DB 사전 -> {"capabilities", "techs", "exclude", "has_other"}. 사용 중(is_active)인 줄만, 능력·기술은 id 순.
    기술의 caps 는 대표 능력(is_primary)이 먼저, 나머지는 능력ID 순(대표가 없으면 능력ID 가 가장 작은 것이 맨 앞).
    꺼진 능력·기술을 가리키는 연결·상위는 뺀다. '기타'는 능력 목록에 넣지 않고 has_other 로만 알린다."""
    caps = conn.execute("SELECT id, name, group_name, aliases, parent_id FROM capability WHERE is_active ORDER BY id").fetchall()
    techs = conn.execute("SELECT id, name, aliases, parent_id FROM tech WHERE is_active ORDER BY id").fetchall()
    cap_name = {r[0]: r[1] for r in caps}
    tech_name = {r[0]: r[1] for r in techs}
    tech_caps: dict[int, list[str]] = {}
    for t, c in conn.execute("SELECT tech_id, capability_id FROM tech_capability ORDER BY tech_id, is_primary DESC, capability_id"):
        if t in tech_name and c in cap_name and cap_name[c] != OTHER:
            tech_caps.setdefault(t, []).append(cap_name[c])
    exclude = {k: [] for k in EXCLUDE_KINDS.values()}
    for kind, word in conn.execute("SELECT kind, word FROM exclude_word ORDER BY id"):
        exclude[EXCLUDE_KINDS[kind]].append(word)
    return {"capabilities": {n: {"group": g, "aliases": list(a), "parent": cap_name.get(p)}
                             for i, n, g, a, p in caps if n != OTHER},
            "techs": {n: {"caps": tech_caps.get(i, []), "aliases": list(a), "parent": tech_name.get(p)} for i, n, a, p in techs},
            "exclude": exclude,
            "has_other": OTHER in cap_name.values()}


def fingerprint(data: dict) -> str:
    """사전 판: 사전 내용(load_dictionary 결과)의 지문 12자리. 내용이 같으면 같다."""
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def check_dictionary(data: dict) -> tuple[list[str], list[str]]:
    """(멈출 이유, 확인 필요). 멈출 이유가 있으면 그 사전으로 추출하면 안 된다(결과가 DB 에 그대로 남음).
    확인 필요: 같은 이름·별칭이 두 기술(또는 두 능력)에 겹침, 상위 고리, 능력이 하나도 없는 사용 중 기술 — 추출은 계속한다."""
    fatal = []
    if not data["capabilities"]:
        fatal.append("사용 중인 능력이 없음")
    if not data["has_other"]:
        fatal.append(f"'{OTHER}' 능력이 없거나 꺼짐")
    if not data["techs"]:
        fatal.append("사용 중인 기술이 없음")
    elif not any(v.get("caps") for v in data["techs"].values()):
        fatal.append("기술과 능력을 잇는 연결이 없음")
    problems = []
    for what, entries in (("기술", data["techs"]), ("능력", data["capabilities"])):
        owner: dict[str, str] = {}
        for name, v in entries.items():
            for k in dict.fromkeys(key(a) for a in [name] + v.get("aliases", [])):
                if owner.setdefault(k, name) != name:
                    problems.append(f"같은 이름·별칭 '{k}' 이 {what} {owner[k]}, {name} 에 겹침 ({owner[k]} 로 씀)")
        cycles = set()
        for name in entries:
            chain, cur = [name], entries[name].get("parent")
            while cur in entries and cur not in chain:
                chain.append(cur)
                cur = entries[cur].get("parent")
            if cur == name and frozenset(chain) not in cycles:
                cycles.add(frozenset(chain))
                problems.append(f"상위 고리: {what} " + " → ".join(chain + [name]))
    problems += [f"능력이 없는 사용 중 기술: {name}" for name, v in data["techs"].items() if not v.get("caps")]
    return fatal, problems


class CapDict:
    def __init__(self, data: dict):
        """data = load_dictionary(conn). 같은 이름·별칭이 겹치면 먼저 나온 것(id 가 작은 것)을 쓴다."""
        d = data
        self.version = fingerprint(d)
        self.capabilities = {k: v for k, v in d["capabilities"].items()}
        self.techs = d["techs"]
        self.cap_by_key, self.tech_by_key = {}, {}
        for name, v in self.capabilities.items():
            for a in [name] + v.get("aliases", []):
                self.cap_by_key.setdefault(key(a), name)
        for name, v in self.techs.items():
            for a in [name] + v.get("aliases", []):
                self.tech_by_key.setdefault(key(a), name)
        ex = d.get("exclude", {})
        # 빈 낱말은 뺀다('' 는 모든 이름 안에 들어 있어서 모든 기술이 빠짐)
        self.llm_patterns = [k for k in (key(p) for p in ex.get("llm_models", [])) if k]
        self.not_skill = {key(x) for x in ex.get("not_skill", [])} - {""}
        self.generic = {key(x) for x in ex.get("generic_words", [])} - {""}

    def cap_names(self) -> list[str]:
        return list(self.capabilities)

    def lookup(self, name: str, _split: bool = True) -> dict:
        k = key(name)
        if not k:
            return {"kind": "unknown", "name": name}
        if any(p in k for p in self.llm_patterns):
            return {"kind": "exclude", "name": name, "reason": "LLM 모델 이름"}
        if k in self.not_skill:
            return {"kind": "exclude", "name": name, "reason": "기술 아님"}
        if k in self.generic:
            return {"kind": "generic", "name": name, "reason": "일반 낱말"}
        if k in self.tech_by_key:
            t = self.tech_by_key[k]
            v = self.techs[t]
            return {"kind": "tech", "name": t, "caps": v.get("caps", []), "parent": v.get("parent")}
        if k in self.cap_by_key:
            return {"kind": "capability", "name": self.cap_by_key[k]}
        if _split:
            parts = [p.strip() for p in re.split(r"[/()·,]", name) if p.strip()]
            if len(parts) > 1:
                looked = [self.lookup(p, _split=False) for p in parts]
                if all(x["kind"] != "unknown" for x in looked):
                    return {"kind": "multi", "name": name, "parts": looked}
        return {"kind": "unknown", "name": name}

    def capability(self, name: str) -> str | None:
        """LLM 이 고른 능력 이름을 표준 이름으로. '기타:' 로 시작하거나 목록 밖이면 None."""
        return self.cap_by_key.get(key(name))

    def satisfies(self, tech_caps: list[str], cap: str) -> bool:
        """기술의 능력 목록이 cap 을 충족하는가(상위 능력 포함: 관계형 DB 는 데이터베이스를 충족)."""
        for c in tech_caps:
            seen = set()   # 팀원이 상위를 고리로 이어도(A → B → A) 끝나게
            while c and c not in seen:
                if c == cap:
                    return True
                seen.add(c)
                c = self.capabilities.get(c, {}).get("parent")
        return False


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import db_load
    with db_load.connect() as conn:
        cd = CapDict(load_dictionary(conn))
    for n in ["AWs", "Kubernetes(K8s)", "RDBMS", "Claude Code", "EC2", "FastAPl", "MyBatis/JPA", "CTO", "Oracle", "Foo"]:
        print(f"{n:<16} -> {cd.lookup(n)}")
    print("Oracle 이 관계형 DB 충족:", cd.satisfies(cd.lookup("Oracle")["caps"], "관계형 DB"),
          "| 데이터베이스 충족:", cd.satisfies(cd.lookup("Oracle")["caps"], "데이터베이스"))
