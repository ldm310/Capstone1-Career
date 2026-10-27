"""
공통 사전(capabilities.json) 조회: 이름 하나를 넣으면 무엇인지 돌려준다.

  kind = tech        구체 기술 (name=표준 이름, caps=속한 능력, parent=상위 기술, 예: EC2 -> AWS)
         capability  능력 이름 자체 (예: RDBMS -> 관계형 DB, NoSQL -> NoSQL DB)
         exclude     스킬이 아님 (LLM 모델 이름, 직무명·약어 등)
         generic     기술 자리에 온 일반 낱말 (AI, Data, 튜닝 등) — 낱말만 빼고 요건은 남긴다
         multi       'Kubernetes(K8s)', 'TCP/UDP' 처럼 여러 개가 붙은 표기 -> parts
         unknown     사전에 없음 (새 기술이거나 OCR 오타 — 사람이 확인)
이름 비교는 대소문자·공백을 무시한다. 공고 쪽과 사용자 쪽이 같은 사전을 써야 맞춰 볼 수 있다.
"""

from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def key(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


class CapDict:
    def __init__(self, path: str = os.path.join(HERE, "capabilities.json")):
        d = json.load(open(path, encoding="utf-8"))
        self.version = d.get("version", "")
        self.capabilities = {k: v for k, v in d["capabilities"].items()}
        self.techs = d["techs"]
        self.cap_by_key, self.tech_by_key = {}, {}
        for name, v in self.capabilities.items():
            for a in [name] + v.get("aliases", []):
                self.cap_by_key[key(a)] = name
        for name, v in self.techs.items():
            for a in [name] + v.get("aliases", []):
                self.tech_by_key[key(a)] = name
        ex = d.get("exclude", {})
        self.llm_patterns = [key(p) for p in ex.get("llm_models", [])]
        self.not_skill = {key(x) for x in ex.get("not_skill", [])}
        self.generic = {key(x) for x in ex.get("generic_words", [])}

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
            while c:
                if c == cap:
                    return True
                c = self.capabilities.get(c, {}).get("parent")
        return False


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cd = CapDict()
    for n in ["AWs", "Kubernetes(K8s)", "RDBMS", "Claude Code", "EC2", "FastAPl", "MyBatis/JPA", "CTO", "Oracle", "Foo"]:
        print(f"{n:<16} -> {cd.lookup(n)}")
    print("Oracle 이 관계형 DB 충족:", cd.satisfies(cd.lookup("Oracle")["caps"], "관계형 DB"),
          "| 데이터베이스 충족:", cd.satisfies(cd.lookup("Oracle")["caps"], "데이터베이스"))
