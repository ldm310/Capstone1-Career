from lv_eval.cli import ROOT
from lv_eval.criteria import load_criteria, adjudicate
from lv_eval.models import CriterionFinding


def test_v2_requires_reproduction_tests_and_analysis():
    table = load_criteria(ROOT / "config/rag.confirmed-v2.json")
    findings = [CriterionFinding(criterion_id=c.id, status="met", rationale="test fixture") for c in table.criteria]
    assert adjudicate(findings, table)[0] == "LV3"
    next(f for f in findings if f.criterion_id == "rag.requirements_tests").status = "unknown"
    assert adjudicate(findings, table)[0] == "LV1"
    next(f for f in findings if f.criterion_id == "rag.reproduction").status = "unknown"
    assert adjudicate(findings, table)[0] is None
    assert "rag.contribution" not in table.levels[0].mandatory_criteria
