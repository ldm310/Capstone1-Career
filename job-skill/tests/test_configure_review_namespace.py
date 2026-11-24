import pytest
from configure_review_namespace import configure

def test_preserves_credentials_and_is_idempotent(tmp_path):
    path=tmp_path/".env"
    path.write_text("RDS_PASSWORD=fake!secret\nOPENAI_API_KEY=fake-test-key\nCAREER_PIPELINE_NAMESPACE=old\n",encoding="utf-8")
    configure(path,"staging")
    once=path.read_text(encoding="utf-8")
    configure(path,"staging")
    assert path.read_text(encoding="utf-8")==once
    assert "RDS_PASSWORD=fake!secret\n" in once
    assert "OPENAI_API_KEY=fake-test-key\n" in once
    assert once.count("CAREER_PIPELINE_NAMESPACE=")==1
    assert once.endswith("CAREER_PIPELINE_NAMESPACE=staging\n")

def test_rejects_missing_env_and_newline_without_mutation(tmp_path):
    path=tmp_path/".env"
    with pytest.raises(ValueError,match="Existing"): configure(path,"staging")
    assert not path.exists()
    path.write_text("original",encoding="utf-8")
    with pytest.raises(ValueError): configure(path,"staging\nOTHER=value")
    assert path.read_text(encoding="utf-8")=="original"
