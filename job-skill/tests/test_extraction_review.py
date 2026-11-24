from uuid import uuid4

import psycopg
import pytest

from extraction_review import ReviewQueue


def test_two_failures_hold_until_feedback_request(db_url):
    queue = ReviewQueue("queue-test", lambda: psycopg.connect(db_url))
    first = queue.begin("T1", {"company":"테스트", "title":"추출 검증"})
    assert first and queue.begin("T1", {}) is None
    queue.finish(first, "형식 오류")
    queue.finish(first, "형식 오류")  # one failed attempt is counted once
    second = queue.begin("T1", {})
    queue.finish(second, "형식 오류")
    assert queue.begin("T1", {}) is None
    with psycopg.connect(db_url) as conn:
        assert conn.execute("SELECT failure_count FROM career_extraction_review WHERE namespace='queue-test'").fetchone()[0] == 2
        conn.execute("UPDATE career_extraction_review SET status='RETRY_REQUESTED',feedback='하단 자격요건을 확인하세요',request_id=%s WHERE namespace='queue-test'", (str(uuid4()),))
    retry = queue.begin("T1", {})
    assert retry["feedback"] == "하단 자격요건을 확인하세요"
    assert queue.begin("T1", {}) is None
    queue.finish(retry)
    with psycopg.connect(db_url) as conn:
        assert conn.execute("SELECT status FROM career_extraction_review WHERE namespace='queue-test'").fetchone()[0] == "RESOLVED"


def test_pass_and_namespace_isolation_and_requested_targets(db_url):
    queue = ReviewQueue("one", lambda: psycopg.connect(db_url))
    ticket = queue.begin("T1", {"company":"예시", "title":"공고"})
    queue.finish(ticket, "형식 오류")
    with psycopg.connect(db_url) as conn:
        conn.execute("UPDATE career_extraction_review SET status='SKIPPED' WHERE namespace='one'")
    assert queue.begin("T1", {}) is None
    assert queue.targets([{"rec_idx":"T1"}, {"rec_idx":"T2"}]) == [{"rec_idx":"T2"}]
    other = ReviewQueue("two", lambda: psycopg.connect(db_url))
    assert other.begin("T1", {}) is not None
    with psycopg.connect(db_url) as conn:
        conn.execute("UPDATE career_extraction_review SET status='RETRY_REQUESTED' WHERE namespace='one'")
    assert queue.requested("T1")
    assert queue.targets([])[0]["rec_idx"] == "T1"


def test_expired_attempt_can_be_recovered_and_old_worker_cannot_finish(db_url):
    queue = ReviewQueue("leases", lambda: psycopg.connect(db_url))
    old = queue.begin("T1", {})
    with psycopg.connect(db_url) as conn:
        conn.execute("UPDATE career_extraction_review SET claimed_at=now()-interval '2 hours' WHERE namespace='leases'")
    current = queue.begin("T1", {})
    assert current and current["attempt"] != old["attempt"]
    queue.finish(old)
    with psycopg.connect(db_url) as conn:
        assert conn.execute("SELECT status,failure_count FROM career_extraction_review WHERE namespace='leases'").fetchone() == ("RUNNING",1)
    queue.finish(current)


def test_admin_feedback_is_present_in_initial_and_validation_retry_input():
    import extract_skills as ex
    inp = {"role":"백엔드", "text":"원문", "review_feedback":"하단 자격요건을 확인하세요"}
    assert inp["review_feedback"] in ex.llm_input(inp)
    retry = ex.llm_input(inp, "직무를 나눠 주세요")
    assert inp["review_feedback"] in retry and "직무를 나눠 주세요" in retry


def test_held_posting_never_calls_extractor(tmp_path, monkeypatch):
    import extract_skills as ex
    class Held:
        def begin(self, *args): return None
    monkeypatch.setattr(ex.ReviewQueue, "configured", lambda: Held())
    monkeypatch.setattr(ex, "EX", str(tmp_path))
    def unexpected(*args): raise AssertionError("Held posting must not call an extractor")
    monkeypatch.setattr(ex, "extract_one", unexpected)
    result = ex.run_model(object(), "gpt-5.6-luna", "low", {"T1":{"text":"원문"}})
    assert result["done_new"] == 0 and result["failed"] == []


def test_all_failed_postings_are_recorded_before_batch_raises(tmp_path, monkeypatch):
    import extract_skills as ex
    finished = []
    class Queue:
        def begin(self, *args): return {"id":1,"attempt":"test","feedback":"하단 확인"}
        def finish(self, ticket, error=None): finished.append(error)
    monkeypatch.setattr(ex.ReviewQueue, "configured", lambda: Queue())
    monkeypatch.setattr(ex, "EX", str(tmp_path))
    def fail(*args):
        assert args[4]["review_feedback"] == "하단 확인"
        raise ValueError("simulated")
    monkeypatch.setattr(ex, "extract_one", fail)
    with pytest.raises(RuntimeError):
        ex.run_model(object(), "gpt-5.6-luna", "low", {"T1":{"text":"원문"}})
    assert finished == ["ValueError"]
