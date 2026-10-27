"""What follow.py appends for a new Quill."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import follow  # noqa: E402


def entry(publisher: str) -> dict:
    return {
        "id": "mail",
        "name": "Mail",
        "summary": "Mail.",
        "repo": "https://github.com/Cloudmorrow/quill-mail",
        "ref": "v1.0.0",
        "category": "communication",
        "publisher": publisher,
    }


def test_one_of_our_own_is_offered_by_the_installer():
    block = follow.add_quill("", entry(follow.ORG))
    assert block.endswith('publisher = "Cloudmorrow"\n# Offered by the installer and the setup page.\nstandard = true\n')
    assert "foundation" not in block, "ticking it to begin with is a hand edit"


def test_somebody_elses_is_not():
    block = follow.add_quill("", entry("Someone"))
    assert "standard" not in block
