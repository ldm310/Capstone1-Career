from lv_eval.cli import ROOT
from lv_eval.criteria import load_criteria, adjudicate
from lv_eval.models import CriterionFinding, EvidenceStatus


def test_user_levels_require_execution_and_do_not_gate_on_contribution():
    table = load_criteria(ROOT / 'config/rag.user-approved.criteria.json')
    findings = [CriterionFinding(criterion_id=c.id, status=EvidenceStatus.MET, rationale='test') for c in table.criteria]
    next(f for f in findings if f.criterion_id == 'rag.contribution').status = EvidenceStatus.UNKNOWN
    assert adjudicate(findings, table)[0] == 'LV3'
    next(f for f in findings if f.criterion_id == 'rag.interpretation').status = EvidenceStatus.UNKNOWN
    assert adjudicate(findings, table)[0] == 'LV2'
    next(f for f in findings if f.criterion_id == 'rag.requirement_tests').status = EvidenceStatus.UNKNOWN
    assert adjudicate(findings, table)[0] == 'LV1'
    next(f for f in findings if f.criterion_id == 'rag.executed').status = EvidenceStatus.UNKNOWN
    assert adjudicate(findings, table)[0] is None
