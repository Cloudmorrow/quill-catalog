"""The review's rules, on install sheets made up for the purpose."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import policy


def plan(**over):
    base = {"id": "plants", "name": "Plants", "version": "1.1.0", "summary": "Your plants.", "license": "MIT",
            "publisher": "you", "code": "", "data": [], "services": [], "webhooks": [], "apis": [], "jobs": [],
            "hooks": [], "machine": [], "runs_code": [], "reach": [], "quill_code": {}}
    base.update(over)
    return base


def test_a_good_update_is_not_refused_and_names_what_changed():
    before = plan(version="1.0.0")
    after = plan(code="quill.py", services=[{"id": "sync"}], quill_code={"fetch": [{"host": "api.example.com"}]},
                 data=[{"id": "plant", "how": "introduces"}, {"id": "contact", "how": "extends"}])
    refused, look = policy.review(before, after, "v1.1.0")
    assert refused == []
    assert any("runs code now" in item for item in look)
    assert any("new services: sync" in item for item in look)
    assert any("api.example.com" in item for item in look)
    assert any("introduces datamodels: plant" in item for item in look)
    assert any("foundational datamodels: contact" in item for item in look)


def test_a_new_quill_is_read_whole():
    refused, look = policy.review(None, plan(), "v1.1.0")
    assert refused == [] and any("a new Quill" in item for item in look)


def test_the_rules():
    old = plan(version="1.1.0")
    refused, _ = policy.review(old, plan(version="1.1.0"), "v1.1.0")
    assert any("not newer" in r for r in refused)
    refused, _ = policy.review(old, plan(version="1.2.0"), "v1.3.0")
    assert any("the release is v1.3.0" in r for r in refused)
    refused, _ = policy.review(old, plan(version="1.2.0", license="Proprietary"), "v1.2.0")
    assert any("licence" in r for r in refused)
    refused, _ = policy.review(old, plan(version="1.2.0", publisher="somebody else"), "v1.2.0")
    assert any("publisher changed" in r for r in refused)
    refused, _ = policy.review(old, plan(version="1.2.0"), "1.2")
    assert any("vMAJOR.MINOR.PATCH" in r for r in refused)
    refused, _ = policy.review(old, plan(version="1.2.0"), "v1.2.0")
    assert refused == []


def test_the_review_is_said_in_markdown():
    text = policy.said(["its licence is not named"], ["it runs code now"])
    assert "Turned down" in text and "- its licence is not named" in text and "Look closely at" in text
    assert "Nothing refused" in policy.said([], [])
