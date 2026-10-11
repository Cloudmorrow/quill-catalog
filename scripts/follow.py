#!/usr/bin/env python3
"""The catalog follows the releases. Run by .github/workflows/releases.yml.

One run, every fifteen minutes and on demand, does the same job for every
Quill and differs only in the last step:

1. It finds the newest release of every Cloudmorrow/quill-* repository (not
   the template), of Cloudmorrow/datamodels, and of every other repository
   catalog.toml lists.
2. For each release newer than the pin, it works out the catalog as it
   should be — a new Cloudmorrow Quill is added, with its name, summary and
   category from quill.toml at that release; an existing one is bumped —
   and runs the check: every Quill fetched at its pin, planned against the
   pinned datamodels, as a server would before installing.
3. Cloudmorrow's Quills and the datamodels: checked out, committed to main.
   The datamodels are bumped only when every Quill still checks out against
   the new release; otherwise the pin stays and the run names the Quill
   that breaks.
4. Everyone else's listed Quills: a pull request, with the check result,
   the review (policy.py: the rules, and what to look closely at) and the
   install sheet in its body. A release that breaks a rule is turned down
   there and then. One of us merges the rest, or closes it; a closed one is
   not opened again, and a pull request somebody opened themselves for the
   same release counts as this one.

This script is the only writer of catalog.toml's refs. The foundation flag
and the categories are product decisions, and stay hand edits: it changes
`ref` lines and appends blocks, and touches nothing else in the file.

    python scripts/follow.py --dry-run     # says what it would do, changes nothing
    python scripts/follow.py               # in Actions, with GH_TOKEN set

The check parses a Quill's Python with `ast` and never runs it, so running
it on a stranger's release here is safe.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import policy
import tomllib

ORG = "Cloudmorrow"
TEMPLATE = "quill-template"
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", f"{ORG}/quill-catalog")
DATAMODELS = f"https://github.com/{ORG}/datamodels"
OURS = re.compile(rf"^https://github\.com/{ORG}/", re.IGNORECASE)
GITHUB = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


# -- GitHub ---------------------------------------------------------------------------
def _request(url: str, accept: str = "application/vnd.github+json") -> bytes | None:
    headers = {"Accept": accept, "User-Agent": "quill-catalog"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def api(path: str):
    data = _request(f"https://api.github.com/{path}")
    return None if data is None else json.loads(data)


def raw(owner: str, name: str, ref: str, path: str) -> str | None:
    data = _request(f"https://raw.githubusercontent.com/{owner}/{name}/{urllib.parse.quote(ref)}/{path}", "*/*")
    return None if data is None else data.decode("utf-8", errors="replace")


def github(repo: str) -> tuple[str, str] | None:
    match = GITHUB.match(repo)
    return (match.group(1), match.group(2)) if match else None


def latest_release(repo: str) -> str | None:
    """The newest release that is neither a draft nor a prerelease; None when there is none."""
    where = github(repo)
    if not where:
        return None
    found = api(f"repos/{where[0]}/{where[1]}/releases/latest")
    return str(found.get("tag_name") or "") or None if found else None


def our_quill_repos() -> list[str]:
    names = []
    page = 1
    while True:
        rows = api(f"orgs/{ORG}/repos?type=public&per_page=100&page={page}") or []
        names += [r["name"] for r in rows if r["name"].startswith("quill-") and not r.get("archived")]
        if len(rows) < 100:
            break
        page += 1
    return sorted(n for n in names if n != TEMPLATE)


# -- versions --------------------------------------------------------------------------
def version_of(tag: str) -> tuple[int, int, int] | None:
    match = VERSION.match(tag or "")
    return tuple(int(n) for n in match.groups()) if match else None  # type: ignore[return-value]


def newer(tag: str, pinned: str) -> bool:
    """A release is newer than the pin when both are versions and it is the greater."""
    a, b = version_of(tag), version_of(pinned)
    return a is not None and (b is None or a > b)


# -- catalog.toml, as text: refs change and blocks are appended, nothing else moves ----
def _blocks(lines: list[str]) -> list[tuple[str, int, int]]:
    heads = [i for i, line in enumerate(lines) if line.startswith("[")] + [len(lines)]
    return [(lines[a].strip(), a, b) for a, b in zip(heads, heads[1:])]


def _is(lines: list[str], a: int, b: int, quill_id: str) -> bool:
    return any(re.match(rf'^id\s*=\s*"{re.escape(quill_id)}"\s*(#.*)?$', line) for line in lines[a:b])


def set_ref(text: str, where: str, ref: str) -> str:
    """*text* with the ref of the datamodels (`where` = "datamodels") or of one Quill set to *ref*."""
    lines = text.split("\n")
    for head, a, b in _blocks(lines):
        if (where == "datamodels" and head == "[datamodels]") or (head == "[[quills]]" and _is(lines, a, b, where)):
            for i in range(a, b):
                match = re.match(r'^(ref\s*=\s*)"[^"]*"(.*)$', lines[i])
                if match:
                    lines[i] = f'{match.group(1)}"{ref}"{match.group(2)}'
                    return "\n".join(lines)
            raise ValueError(f"{where} has no ref line")
    raise ValueError(f"{where} is not in the catalog")


def add_quill(text: str, entry: dict) -> str:
    block = ["", "[[quills]]"] + [f"{key} = {json.dumps(entry[key], ensure_ascii=False)}" for key in
                                  ("id", "name", "summary", "repo", "ref", "category", "publisher")]
    return text.rstrip("\n") + "\n" + "\n".join(block) + "\n"


# -- the check: what check.yml does, kept per Quill -----------------------------------
class Checker:
    """Fetches once per (repo, ref) and plans every Quill of a catalog; the results per id."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.fetched: dict[tuple[str, str], Path | Exception] = {}
        self.count = 0

    def folder(self, repo: str, ref: str) -> Path:
        from cloudmorrow.server.quills import fetch

        key = (repo, ref)
        if key not in self.fetched:
            self.count += 1
            try:
                self.fetched[key] = fetch(repo, ref, into=self.tmp / f"fetch-{self.count}")
            except Exception as exc:  # kept, so one bad release is reported once per run
                self.fetched[key] = exc
        found = self.fetched[key]
        if isinstance(found, Exception):
            raise found
        return found

    def run(self, data: dict) -> dict[str, dict]:
        from cloudmorrow.server.quills import QuillRegistry

        results: dict[str, dict] = {}
        categories = {c.get("id") for c in data.get("categories", [])}
        try:
            models = self.folder(data["datamodels"]["repo"], data["datamodels"]["ref"])
        except Exception as exc:
            return {e["id"]: {"ok": False, "error": f"the datamodels could not be fetched: {exc}"}
                    for e in data.get("quills", [])}
        for entry in data.get("quills", []):
            quill_id = entry["id"]
            try:
                if quill_id in results:
                    raise ValueError(f"{quill_id} is listed twice")
                if entry.get("category") not in categories:
                    raise ValueError(f"{entry.get('category')!r} is not a category of the catalog")
                folder = self.folder(entry["repo"], entry["ref"])
                self.count += 1
                registry = QuillRegistry(self.tmp / f"reg-{self.count}" / "quills", self.tmp / f"reg-{self.count}" / "models")
                plan = registry.plan(folder, models)
                if plan["id"] != quill_id:
                    raise ValueError(f"{entry['repo']} is {plan['id']}, not {quill_id}")
                results[quill_id] = {"ok": True, "version": plan["version"], "plan": plan}
            except Exception as exc:
                results[quill_id] = {"ok": False, "error": f"{exc}"}
        return results


def failures(results: dict[str, dict]) -> dict[str, str]:
    return {k: v["error"] for k, v in results.items() if not v["ok"]}


# -- the install sheet, as Markdown: what a fresh server would show before saying yes ---
def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def sheet(plan: dict) -> str:
    rows: list[tuple[str, str, str]] = []
    for row in plan.get("data", []):
        what = f"{row['how']} `{row['id']}`" + (f" ({', '.join(row['fields'])})" if row.get("fields") else "")
        note = "new here" if row.get("new") else ""
        if row.get("why"):
            note = f"{row.get('access', '')}: {row['why']}"
        rows.append(("datamodel", what, note))
    for screen in plan.get("screens", []):
        rows.append(("screen", f"{screen.get('label') or screen['id']} ({screen.get('kit', 'view')})",
                     "on " + ", ".join(plan.get("surfaces", []))))
    for job in plan.get("jobs", []):
        rows.append(("job", job["id"], f"{job.get('action', '')} {job.get('model', '')}".strip()))
    for dataset in plan.get("datasets", []):
        rows.append(("dataset", dataset["id"], f"{dataset['count']} {dataset['model']} ({dataset['seed']})"))
    for service in plan.get("services", []):
        rows.append(("service", service["id"], " ".join(service.get("command", [])) + (", kept running" if service.get("always") else "")))
    for hook in plan.get("webhooks", []):
        target = f"→ {hook['model']}" if hook.get("model") else f"→ {hook['handler']}()" if hook.get("handler") else f"→ {hook.get('forward')}"
        rows.append(("webhook", hook["id"], f"POST /hooks/{plan['id']}/{hook.get('path', '')} {target}"))
    for one in plan.get("apis", []):
        rows.append(("api", one["id"], f"/api/q/{plan['id']}/… → " + (f"{one['handler']}()" if one.get("handler") else str(one.get("service", "")))))
    for action in plan.get("actions", []):
        on = f" on a {action['on']}" if action.get("on") else ""
        takes = ", ".join(f["name"] for f in action.get("fields", [])) or "nothing"
        rows.append(("action", action.get("label") or action["id"], f"{action.get('handler', action['id'])}(){on}, takes {takes}"))
    for hook in plan.get("hooks", []):
        rows.append(("hook", f"{hook['handler']}()", f"when a {hook['on']} is {' or '.join(hook.get('when', []))}"))
    for machine in plan.get("machine", []):
        folders = ", ".join(f"{f['name']} ({f['access']})" for f in machine.get("folders", [])) or "no folders"
        rows.append(("on a machine", machine["id"], f"{machine.get('why', '')} — {folders}"))

    lines = [f"**{plan['name']} {plan['version']}** — {plan.get('summary') or ''}", ""]
    if rows:
        lines += ["| | what it adds | |", "|---|---|---|"]
        lines += [f"| {_cell(a)} | {_cell(b)} | {_cell(c)} |" for a, b, c in rows]
        lines.append("")
    code = plan.get("quill_code") or {}
    if code:
        lines.append(f"Its Python runs in a sandbox, as whoever uses it: `{plan.get('code', '')}`.")
        lines += [f"- reaches {item['host']} — {item['why']}" for item in code.get("fetch", [])]
        lines += [f"- reads your secret {item['key']} — {item['why']}" for item in code.get("secrets", [])]
    if plan.get("runs_code") or plan.get("webhooks"):
        who = plan.get("runs_as") or "the administrator who installs it"
        reach = ", ".join(plan.get("reach") or []) or "nothing"
        if plan.get("runs_code"):
            lines.append(f"**Runs code on this server:** {'; '.join(plan['runs_code'])}")
        lines.append(f"It runs as {who}, and can read and write only: {reach}.")
    return "\n".join(lines).rstrip() + "\n"


def compare_url(repo: str, before: str, after: str) -> str:
    return f"{repo.rstrip('/')}/compare/{before}...{after}" if before else f"{repo.rstrip('/')}/tree/{after}"


# -- git and pull requests ----------------------------------------------------------------
def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True).stdout.strip()


def commit(path: Path, text: str, title: str, body: str, dry: bool) -> None:
    if dry:
        print(f"\n--- would commit: {title}\n{body}")
        return
    path.write_text(text, encoding="utf-8")
    git("add", str(path))
    git("-c", f"user.name={BOT[0]}", "-c", f"user.email={BOT[1]}", "commit", "-q", "-m", title, "-m", body)


def pull_request_exists(quill_id: str, ref: str, branch: str) -> str:
    """Why no pull request is opened: one waits already, or one for this release was closed."""
    owner, name = REPOSITORY.split("/")
    for pr in api(f"repos/{REPOSITORY}/pulls?state=open&per_page=100") or []:
        head = pr.get("head") or {}
        if head.get("ref") == branch and (head.get("repo") or {}).get("full_name") == REPOSITORY:
            return f"#{pr['number']} waits already"
        full = (head.get("repo") or {}).get("full_name") or ""
        if "/" in full and head.get("sha"):
            text = raw(*full.split("/", 1), head["sha"], "catalog.toml")
            try:
                theirs = tomllib.loads(text or "")
            except tomllib.TOMLDecodeError:
                continue
            for entry in theirs.get("quills", []):
                if entry.get("id") == quill_id and entry.get("ref") == ref:
                    return f"#{pr['number']} by {(pr.get('user') or {}).get('login', '?')} waits already"
    closed = api(f"repos/{REPOSITORY}/pulls?state=closed&head={owner}:{urllib.parse.quote(branch)}&per_page=5") or []
    for pr in closed:
        if not pr.get("merged_at"):
            return f"turned down in #{pr['number']}"
    return ""


def open_pull_request(branch: str, title: str, body: str, dry: bool) -> str:
    if dry:
        print(f"\n--- would open a pull request from {branch}: {title}\n{body}")
        return "(dry run)"
    git("push", "-f", "-q", "origin", f"HEAD:refs/heads/{branch}")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
        handle.write(body)
    out = subprocess.run(
        ["gh", "pr", "create", "--base", "main", "--head", branch, "--title", title, "--body-file", handle.name],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return out


def close_pull_request(url: str, comment: str, dry: bool) -> None:
    if dry:
        print(f"\n--- would close it: {comment}")
        return
    subprocess.run(["gh", "pr", "close", url, "--comment", comment], check=True, capture_output=True, text=True)


# -- the run -------------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalog", default="catalog.toml", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="say what would be done; commit and open nothing")
    parser.add_argument("--ours", default=OURS.pattern, help="the repositories committed without review (a regex)")
    args = parser.parse_args()
    ours = re.compile(args.ours, re.IGNORECASE)
    path: Path = args.catalog
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    report: list[str] = []
    say = lambda line: (print(line), report.append(line))

    ids = {e["id"]: e for e in data.get("quills", [])}
    by_repo = {e["repo"].rstrip("/").removesuffix(".git").lower(): e for e in data.get("quills", [])}
    categories = {c.get("id") for c in data.get("categories", [])}
    names = {e["id"]: e.get("name") or e["id"] for e in data.get("quills", [])}

    # 1. The releases there are, and what the catalog pins.
    datamodels_new = None
    tag = latest_release(data["datamodels"]["repo"])
    if tag and newer(tag, data["datamodels"]["ref"]):
        datamodels_new = tag
    bumps: dict[str, tuple[str, str]] = {}  # id -> (pinned, new): ours, committed
    others: list[tuple[dict, str]] = []  # everyone else's: a pull request each
    for entry in data.get("quills", []):
        tag = latest_release(entry["repo"])
        if tag and newer(tag, entry["ref"]):
            if ours.match(entry["repo"]):
                bumps[entry["id"]] = (entry["ref"], tag)
            else:
                others.append((entry, tag))
    adds: list[dict] = []  # ours that are not listed yet
    for name in our_quill_repos() if args.ours == OURS.pattern else []:
        repo = f"https://github.com/{ORG}/{name}"
        if repo.lower() in by_repo:
            continue
        tag = latest_release(repo)
        if not tag:
            continue
        manifest_text = raw(ORG, name, tag, "quill.toml")
        try:
            quill = tomllib.loads(manifest_text or "").get("quill", {})
        except tomllib.TOMLDecodeError as exc:
            say(f"- {name} {tag}: its quill.toml does not parse ({exc}); not added")
            continue
        quill_id = str(quill.get("id") or "")
        if not quill_id or quill_id in ids:
            say(f"- {name} {tag}: its id {quill_id!r} is missing or already listed from another repository; not added")
            continue
        if quill.get("category") not in categories:
            say(f"- {name} {tag}: quill.toml names no category of the catalog ({quill.get('category')!r}); "
                f"add it by hand with one")
            continue
        adds.append({
            "id": quill_id, "name": str(quill.get("name") or quill_id), "summary": str(quill.get("summary") or ""),
            "repo": repo, "ref": tag, "category": str(quill["category"]), "publisher": str(quill.get("publisher") or ORG),
        })
        names[quill_id] = adds[-1]["name"]

    if not (datamodels_new or bumps or adds or others):
        say("Nothing new: every pin is the newest release.")
        return finish(report)

    with tempfile.TemporaryDirectory(prefix="quill-catalog-") as tmp:
        checker = Checker(Path(tmp))

        # 2. and 3. Ours and the datamodels: worked out, checked, committed.
        held: dict[str, str] = {}
        if datamodels_new or bumps or adds:
            def compose(with_datamodels: bool, skip: set[str]) -> str:
                new = text
                if with_datamodels and datamodels_new:
                    new = set_ref(new, "datamodels", datamodels_new)
                for quill_id, (_, tag) in bumps.items():
                    if quill_id not in skip:
                        new = set_ref(new, quill_id, tag)
                for entry in adds:
                    if entry["id"] not in skip:
                        new = add_quill(new, entry)
                return new

            with_datamodels = bool(datamodels_new)
            skip: set[str] = set()
            new = compose(with_datamodels, skip)
            bad = failures(checker.run(tomllib.loads(new)))
            if bad and with_datamodels:
                # Without the datamodels bump: what still fails is the Quill's own fault.
                without = failures(checker.run(tomllib.loads(compose(False, skip))))
                because_of_datamodels = {k: v for k, v in bad.items() if k not in without}
                if because_of_datamodels:
                    with_datamodels = False
                    held["datamodels"] = "; ".join(f"{k}: {v}" for k, v in because_of_datamodels.items())
                bad = without
            if bad:
                skip = {k for k in bad if k in bumps or k in {e["id"] for e in adds}}
                held.update({k: bad[k] for k in skip})
                # A Quill that fails on main as it is today is somebody's to fix by
                # hand; it does not hold up the releases that do check out.
                already = failures(checker.run(data))
                for k, v in bad.items():
                    if k not in skip and k in already:
                        say(f"- {k} fails on main already, before any of this: {v}")
                stuck = {k: v for k, v in bad.items() if k not in skip and k not in already}
                if stuck:
                    say("The catalog as it would be does not check out; nothing is committed:")
                    for k, v in stuck.items():
                        say(f"- {k}: {v}")
                    return finish(report, 1)
                new = compose(with_datamodels, skip)
                bad = {k: v for k, v in failures(checker.run(tomllib.loads(new))).items() if k not in already}
                if bad:
                    say("The catalog does not check out even with the failing releases held back; nothing is committed:")
                    for k, v in bad.items():
                        say(f"- {k}: {v}")
                    return finish(report, 1)

            taken = [f"{names[k]} {v[1].lstrip('v')}" for k, v in bumps.items() if k not in skip]
            taken += [f"{e['name']} {e['ref'].lstrip('v')} (new)" for e in adds if e["id"] not in skip]
            if with_datamodels and datamodels_new:
                taken.append(f"the datamodels at {datamodels_new}")
            if new != text:
                lines = [f"{names[k]}: {v[0]} → {v[1]}  {compare_url(ids[k]['repo'], v[0], v[1])}"
                         for k, v in bumps.items() if k not in skip]
                lines += [f"{e['name']}: new, at {e['ref']}  {e['repo']}/tree/{e['ref']}" for e in adds if e["id"] not in skip]
                if with_datamodels and datamodels_new:
                    lines.append(f"datamodels: {data['datamodels']['ref']} → {datamodels_new}  "
                                 f"{compare_url(DATAMODELS, data['datamodels']['ref'], datamodels_new)}")
                title = ", ".join(taken[:-1]) + (" and " if len(taken) > 1 else "") + taken[-1]
                title = title[0].upper() + title[1:]
                body = "Checked: every Quill at its pin against the pinned datamodels.\n\n" + "\n".join(lines) + \
                       "\n\nCommitted by the releases workflow (scripts/follow.py)."
                commit(path, new, title, body, args.dry_run)
                if not args.dry_run:
                    git("push", "-q", "origin", "HEAD:main")
                say(f"Committed to main: {title}.")
                text, data = new, tomllib.loads(new)
            for what, why in held.items():
                if what == "datamodels":
                    say(f"- the datamodels stay at {data['datamodels']['ref']}: {datamodels_new} breaks {why}")
                else:
                    where = bumps.get(what, ("", next((e["ref"] for e in adds if e["id"] == what), "")))[1]
                    say(f"- {names.get(what, what)} {where} is not taken: {why}")

        # 4. Everyone else's: a pull request each, with the check and the install sheet.
        base = git("rev-parse", "HEAD") if not args.dry_run else ""
        pinned_plans = checker.run(data) if others else {}
        for entry, tag in others:
            quill_id, repo, pinned = entry["id"], entry["repo"], entry["ref"]
            branch = f"release/{quill_id}-{tag.lstrip('v')}"
            why_not = pull_request_exists(quill_id, tag, branch)
            if why_not:
                say(f"- {names[quill_id]} {tag}: {why_not}")
                continue
            new = set_ref(text, quill_id, tag)
            results = checker.run(tomllib.loads(new))
            bad = failures(results)
            mine = results.get(quill_id) or {}
            title = f"{names[quill_id]} {tag.lstrip('v')}"
            body = [f"{repo} released [{tag}]({repo.rstrip('/')}/releases/tag/{tag}); the catalog pins {pinned}. "
                    f"[What changed]({compare_url(repo, pinned, tag)}).", ""]
            if bad:
                body += ["**✗ The check fails:**", ""] + [f"- {k}: {v}" for k, v in bad.items()] + [""]
            else:
                body += ["**✓ Every Quill checks out** at its pin against the pinned datamodels, this one at "
                         f"{tag}.", ""]
            refused: list[str] = []
            if mine.get("plan"):
                refused, look = policy.review((pinned_plans.get(quill_id) or {}).get("plan"), mine["plan"], tag, listed=True)
                body += [policy.said(refused, look), "## The install sheet", "", sheet(mine["plan"])]
            body += ["---", "Opened by the releases workflow. Merging takes the release into the catalog; closing "
                     "turns it down, and the workflow does not open it again."]
            if not args.dry_run:
                git("checkout", "-q", "-B", branch, base)
            try:
                commit(path, new, title, f"{repo}: {pinned} → {tag}", args.dry_run)
                url = open_pull_request(branch, title, "\n".join(body), args.dry_run)
                if refused:
                    # Turned down by the rules: closed at once, with the reasons where the
                    # author reads them, and never opened again for this release.
                    close_pull_request(url, "Turned down by the review's rules: " + "; ".join(refused) + ".", args.dry_run)
            finally:
                if not args.dry_run:
                    git("checkout", "-q", "--detach", base)
            said = f"- {title}: pull request {url}"
            if refused:
                said += " — turned down: " + "; ".join(refused)
            elif bad:
                said += " (the check fails; see its body)"
            say(said)
    return finish(report)


def finish(report: list[str], code: int = 0) -> int:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(report) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
