"""The review of a release: what is refused outright, and what to look closely at.

Every release of a Quill that is not Cloudmorrow's is reviewed before the
catalog takes it. Part of that review is fixed rules, applied by the
workflow to every pull request: a release that breaks one is turned down
with the reason, whoever opened the pull request. The rest is a person
reading the Quill at that release, helped by a list of what changed in the
ways that matter: code that was not there before, a service, a webhook, a
host it reaches, a secret it reads, a datamodel it adds or extends.

`review(before, after, tag)` takes the install sheets (`QuillRegistry.plan`)
of the pinned release and of the new one — `before` is None for a Quill
that is new to the catalog — and returns `(refused, look)`: the rules the
release breaks, and the things a reviewer should look at.
"""

from __future__ import annotations

import re

VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

# Licences the catalog lists: every Quill in it is free and open source.
OPEN_LICENSES = {
    "AGPL-3.0-only", "AGPL-3.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later", "GPL-2.0-only",
    "GPL-2.0-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later", "LGPL-2.1-only", "LGPL-2.1-or-later",
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "ISC", "EUPL-1.2", "Unlicense", "CC0-1.0",
}


def version_of(tag: str) -> tuple[int, int, int] | None:
    match = VERSION.match(tag or "")
    return tuple(int(n) for n in match.groups()) if match else None  # type: ignore[return-value]


def _ids(rows, key="id") -> set[str]:
    return {str(r.get(key, "")) for r in (rows or []) if isinstance(r, dict)}


def _hosts(plan: dict) -> set[str]:
    code = plan.get("quill_code") or {}
    return {str(f.get("host", "")) for f in code.get("fetch", []) if isinstance(f, dict)}


def _secrets(plan: dict) -> set[str]:
    code = plan.get("quill_code") or {}
    return {str(s.get("key", "")) for s in code.get("secrets", []) if isinstance(s, dict)}


def _extended(plan: dict) -> set[str]:
    return {str(r.get("id", "")) for r in plan.get("data", []) if isinstance(r, dict) and r.get("how") == "extends"}


def _introduced(plan: dict) -> set[str]:
    return {str(r.get("id", "")) for r in plan.get("data", []) if isinstance(r, dict) and r.get("how") == "introduces"}


def review(before: dict | None, after: dict, tag: str, *, listed: bool | None = None) -> tuple[list[str], list[str]]:
    """*listed* says the Quill is in the catalog already even when its pinned release
    could not be planned (*before* is None then): it is not a new Quill, but one whose
    old release a reviewer cannot be shown the difference from."""
    refused: list[str] = []
    look: list[str] = []
    listed = bool(before) if listed is None else listed

    # -- the rules ---------------------------------------------------------------------
    version = str(after.get("version", ""))
    if version_of(tag) is None:
        refused.append(f"the release is {tag}; a release is a tag vMAJOR.MINOR.PATCH")
    elif version_of(f"v{version}") != version_of(tag):
        refused.append(f"quill.toml says version {version}, the release is {tag}")
    licence = str(after.get("license", "")).strip()
    if licence not in OPEN_LICENSES:
        refused.append(f"its licence is {licence or 'not named'}; every Quill in the catalog is open source "
                       f"({', '.join(sorted(OPEN_LICENSES))})")
    if not str(after.get("summary", "")).strip():
        refused.append("quill.toml has no summary")
    if before:
        if version_of(f"v{version}") is not None and version_of(f"v{before.get('version', '')}") is not None \
                and version_of(f"v{version}") <= version_of(f"v{before['version']}"):  # type: ignore[operator]
            refused.append(f"version {version} is not newer than the catalog's {before.get('version')}")
        if str(before.get("publisher", "")) != str(after.get("publisher", "")):
            refused.append(f"the publisher changed from {before.get('publisher')!r} to {after.get('publisher')!r}; "
                           f"a Quill that changes hands is a pull request from the new publisher, saying so")
        if str(before.get("license", "")) != licence:
            look.append(f"the licence changed from {before.get('license')} to {licence}")

    # -- what to look closely at ---------------------------------------------------------
    old = before or {}
    if after.get("code") and not old.get("code"):
        look.append(f"it runs code now (`{after['code']}`); it did not before")
    for kind in ("services", "webhooks", "apis", "jobs", "hooks", "machine"):
        new = _ids(after.get(kind)) - _ids(old.get(kind))
        if new:
            what = {"services": "services", "webhooks": "webhooks", "apis": "APIs", "jobs": "jobs",
                    "hooks": "hooks on records", "machine": "handlers on a person's machine"}[kind]
            look.append(f"new {what}: {', '.join(sorted(new))}")
    if set(after.get("runs_code") or []) - set(old.get("runs_code") or []):
        look.append("it runs code on the server itself: " + "; ".join(after.get("runs_code") or []))
    hosts = _hosts(after) - _hosts(old)
    if hosts:
        look.append("it reaches hosts it did not before: " + ", ".join(sorted(hosts)))
    secrets = _secrets(after) - _secrets(old)
    if secrets:
        look.append("it reads secrets it did not before: " + ", ".join(sorted(secrets)))
    extended = _extended(after) - _extended(old)
    if extended:
        look.append("it adds fields to foundational datamodels: " + ", ".join(sorted(extended)))
    introduced = _introduced(after) - _introduced(old)
    if introduced:
        look.append("it introduces datamodels: " + ", ".join(sorted(introduced)))
    reach = set(after.get("reach") or []) - set(old.get("reach") or [])
    if before and reach:
        look.append("its code reaches more datamodels: " + ", ".join(sorted(reach)))
    if before and str(before.get("name")) != str(after.get("name")):
        look.append(f"it is called {after.get('name')!r} now, not {before.get('name')!r}")
    if not listed:
        look.append("a new Quill: read the whole of it, and that its README says what the install sheet says")
    elif not before:
        look.append("the release the catalog pins could not be planned against today's datamodels, so this is "
                    "the whole of it, not what changed")
    return refused, look


def said(refused: list[str], look: list[str]) -> str:
    """The review, as Markdown for a pull request body or comment."""
    lines = ["## The review", ""]
    if refused:
        lines += ["**✗ Turned down.** The catalog does not take this release:", ""]
        lines += [f"- {r}" for r in refused]
        lines.append("")
        lines.append("Fix it and release again; the next release is looked at afresh.")
    else:
        lines.append("**✓ Nothing refused by the rules.** It is reviewed before it is merged.")
    if look:
        lines += ["", "Look closely at:", ""] + [f"- {item}" for item in look]
    return "\n".join(lines) + "\n"
