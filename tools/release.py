"""Cut a release: `just release [--dry-run] [X.Y.Z]`. The process is in
design/engineering-foundations.md.

Collects the `## Changelog` bullets of the PRs merged since the last `v*` tag, works out the next
version from them, runs `just check`, then opens a `release/vX.Y.Z` PR that bumps the version and
adds the release notes to CHANGELOG.md. `--notes X.Y.Z` prints a version's section of
CHANGELOG.md, for the release workflow. Standard library only, so CI can run it with any Python.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

TAGS = ("Added", "Changed", "Removed", "Fixed", "Security")
VERSION = re.compile(r"\d+\.\d+\.\d+")
CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

Bullet = tuple[str, str]


def bullets(body: str) -> list[Bullet]:
    """The (tag, text) bullets in a PR body's `## Changelog` section, untagged ones as Changed.
    Skips HTML comments, empty bullets and "No user-facing change"."""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    match = re.search(r"^##\s+Changelog\s*$(.*?)(?=^#{1,2}\s|\Z)", body, re.M | re.S | re.I)
    if not match:
        return []
    items: list[str] = []
    for line in match.group(1).splitlines():
        if re.match(r"[-*]\s", line):
            items.append(line[2:].strip())
        elif items and line[:1].isspace() and line.strip():
            items[-1] += " " + line.strip()
    found = []
    for item in items:
        tag = re.match(r"\[(\w+)\]\s*", item)
        name, text = ("Changed", item)
        if tag and (named := tag.group(1).capitalize()) in TAGS:
            name, text = named, item[tag.end() :]
        found.append((name, re.sub(r"^breaking:", "Breaking:", text, flags=re.I)))
    return [
        (tag, text)
        for tag, text in found
        if text and text.rstrip(".").lower() != "no user-facing change"
    ]


def next_version(current: str, found: list[Bullet]) -> tuple[str, str]:
    """The version after `current` that `found` calls for, and why."""
    major, minor, patch = (int(n) for n in current.split("."))
    if any(tag == "Removed" or text.startswith("Breaking:") for tag, text in found):
        reason = "a [Removed] or Breaking: bullet is a major bump"
        if major == 0:
            return f"0.{minor + 1}.0", reason + ", a minor one before 1.0"
        return f"{major + 1}.0.0", reason
    if any(tag == "Added" for tag, _ in found):
        return f"{major}.{minor + 1}.0", "an [Added] bullet is a minor bump"
    return f"{major}.{minor}.{patch + 1}", "no [Added], [Removed] or Breaking: bullets is a patch"


def notes(found: list[Bullet]) -> str:
    """Release notes: the bullets grouped under a heading per tag, without repeats."""
    groups: dict[str, list[str]] = {tag: [] for tag in TAGS}
    seen = set()
    for tag, text in found:
        key = (tag, " ".join(text.lower().split()))
        if key not in seen:
            seen.add(key)
            groups[tag].append(" ".join(text.split()))
    return "\n".join(
        f"### {tag}\n\n" + "".join(f"- {text}\n" for text in texts)
        for tag, texts in groups.items()
        if texts
    )


def section(changelog: str, version: str) -> str | None:
    """The body of a version's section in CHANGELOG.md, or None if it has none."""
    match = re.search(rf"^## {re.escape(version)} .*?\n\n(.*?)(?=\n## |\Z)", changelog, re.M | re.S)
    return match.group(1) if match else None


def add_section(changelog: str, version: str, day: date, body: str) -> str:
    """CHANGELOG.md with a section for `version` below `## Unreleased`, unchanged if it has one."""
    if section(changelog, version) is not None:
        return changelog
    head, unreleased, tail = changelog.partition("## Unreleased\n")
    if not unreleased:
        raise ValueError("CHANGELOG.md has no '## Unreleased' heading.")
    tail = tail.lstrip("\n")
    return f"{head}{unreleased}\n## {version} - {day.isoformat()}\n\n{body}" + (
        f"\n{tail}" if tail else ""
    )


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def ok(*args: str) -> bool:
    return subprocess.run(args, capture_output=True).returncode == 0


def collect() -> tuple[str, list[int], list[Bullet]]:
    """The last released version, and the PRs and bullets merged into origin/main since."""
    tag = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", "origin/main"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    commits = set(run("git", "rev-list", f"{tag}..origin/main" if tag else "origin/main").split())
    prs = json.loads(
        run("gh", "pr", "list", "--state", "merged", "--base", "main", "--limit", "1000",
            "--json", "number,body,mergeCommit")
    )  # fmt: skip
    shipped = sorted(
        (pr for pr in prs if (pr["mergeCommit"] or {}).get("oid") in commits),
        key=lambda pr: pr["number"],
    )
    found = [bullet for pr in shipped for bullet in bullets(pr["body"])]
    return tag.removeprefix("v") or "0.0.0", [pr["number"] for pr in shipped], found


def problems(version: str, current: str, found: list[Bullet]) -> list[str]:
    """Why this release can't be cut, if anything stops it."""
    found_problems = []
    if run("git", "branch", "--show-current") != "main":
        found_problems.append("not on main")
    if run("git", "status", "--porcelain"):
        found_problems.append("the working tree has uncommitted changes")
    if run("git", "rev-parse", "HEAD") != run("git", "rev-parse", "origin/main"):
        found_problems.append("main is not the same as origin/main")
    if not found:
        found_problems.append("no changelog bullets to ship since the last release")
    if not VERSION.fullmatch(version):
        found_problems.append(f"{version} is not X.Y.Z")
    elif tuple(map(int, version.split("."))) <= tuple(map(int, current.split("."))):
        found_problems.append(f"{version} is not after {current}")
    if ok("git", "rev-parse", "-q", "--verify", f"refs/tags/v{version}") or run(
        "git", "ls-remote", "--tags", "origin", f"v{version}"
    ):
        found_problems.append(f"tag v{version} already exists")
    if ok("git", "rev-parse", "-q", "--verify", f"refs/heads/release/v{version}") or run(
        "git", "ls-remote", "--heads", "origin", f"release/v{version}"
    ):
        found_problems.append(f"branch release/v{version} already exists")
    return found_problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="just release", description=__doc__.split("\n\n")[0])
    parser.add_argument("version", nargs="?", help="X.Y.Z, instead of the calculated version")
    parser.add_argument("--dry-run", action="store_true", help="check and print, change nothing")
    parser.add_argument("--notes", metavar="X.Y.Z", help="print a version's CHANGELOG.md section")
    args = parser.parse_args(argv)

    if args.notes:
        body = section(CHANGELOG.read_text(), args.notes)
        if body is None:
            sys.exit(f"CHANGELOG.md has no section for {args.notes}.")
        print(body, end="")
        return 0

    run("git", "fetch", "--quiet", "--tags", "origin")
    current, numbers, found = collect()
    version, reason = (args.version, "given") if args.version else next_version(current, found)
    stops = problems(version, current, found)
    if stops and not args.dry_run:
        sys.exit("Refusing to release: " + "; ".join(stops) + ".")

    checked = subprocess.run(["just", "check"]).returncode == 0
    prs = ", ".join(f"#{n}" for n in numbers) or "none"
    print(f"\nLast release: {current}. PRs merged since: {prs}.")
    print(f"Next version: {version} ({reason}).\n\nRelease notes:\n\n{notes(found)}")
    if args.dry_run:
        stops += [] if checked else ["just check failed"]
        for stop in stops:
            print(f"Would refuse: {stop}.")
        print(
            f"Dry run, nothing changed. A release would create branch release/v{version} with "
            f"{version} in pyproject.toml and uv.lock and these notes in CHANGELOG.md, push it "
            "and open its PR."
        )
        return 1 if stops else 0
    if not checked:
        sys.exit("Refusing to release: just check failed.")

    branch = f"release/v{version}"
    today = datetime.now(timezone.utc).date()
    run("git", "switch", "-c", branch)
    run("uv", "version", version)
    CHANGELOG.write_text(add_section(CHANGELOG.read_text(), version, today, notes(found)))
    run("git", "commit", "-am", f"Release {version}")
    run("git", "push", "-u", "origin", branch)
    body = (
        f"Merging this tags v{version} on the merge commit, publishes {version} to PyPI and "
        f"creates the GitHub Release with these notes, already added to CHANGELOG.md:\n\n"
        f"{notes(found)}"
    )
    print(run("gh", "pr", "create", "--base", "main", "--title", f"Release {version}",
              "--body", body))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
