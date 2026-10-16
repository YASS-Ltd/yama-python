"""The pure half of `just release`: collecting changelog bullets, choosing the next version and
writing the release notes into CHANGELOG.md."""

from datetime import date

import pytest

from tools.release import add_section, bullets, next_version, notes, section

BODY = """\
Some summary.

## Changelog

<!--
One bullet per change. [Added] is an example tag.
- [Added] not a bullet
-->
- [Added] Paging
  that wraps.
* [Fixed] A bug
- No tag at all
- [Added]
- No user-facing change.

🤖 Generated with a tool

## Notes

- [Added] Not in the changelog section
"""


def test_bullets_come_from_the_changelog_section_only() -> None:
    assert bullets(BODY) == [
        ("Added", "Paging that wraps."),
        ("Fixed", "A bug"),
        ("Changed", "No tag at all"),
    ]


def test_bullets_without_a_section_are_empty() -> None:
    assert bullets("## Summary\n\n- [Added] something\n") == []
    assert bullets("") == []


@pytest.mark.parametrize(
    ("current", "found", "expected"),
    [
        ("0.0.0", [("Added", "x"), ("Fixed", "y")], "0.1.0"),
        ("0.1.0", [("Fixed", "y")], "0.1.1"),
        ("0.1.3", [("Changed", "y"), ("Security", "z")], "0.1.4"),
        ("0.1.3", [("Removed", "y")], "0.2.0"),
        ("0.1.3", [("Changed", "Breaking: renamed x")], "0.2.0"),
        ("1.2.3", [("Added", "x")], "1.3.0"),
        ("1.2.3", [("Changed", "Breaking: renamed x")], "2.0.0"),
        ("1.2.3", [("Removed", "x"), ("Added", "y")], "2.0.0"),
    ],
)
def test_next_version_follows_the_bullets(
    current: str, found: list[tuple[str, str]], expected: str
) -> None:
    assert next_version(current, found)[0] == expected


def test_next_version_explains_itself() -> None:
    assert next_version("0.1.0", [("Removed", "x")])[1] == (
        "a [Removed] or Breaking: bullet is a major bump, a minor one before 1.0"
    )


def test_notes_group_by_tag_and_drop_duplicates() -> None:
    found = [
        ("Fixed", "A bug"),
        ("Added", "Paging"),
        ("Fixed", "A  bug"),
        ("Added", "Retries"),
    ]
    assert notes(found) == "### Added\n\n- Paging\n- Retries\n\n### Fixed\n\n- A bug\n"


CHANGELOG = "# Changelog\n\nIntro.\n\n## Unreleased\n\n## 0.1.0 - 2026-10-01\n\n- Old\n"


def test_add_section_goes_below_unreleased() -> None:
    updated = add_section(CHANGELOG, "0.2.0", date(2026, 10, 16), "### Fixed\n\n- A bug\n")
    assert updated == (
        "# Changelog\n\nIntro.\n\n## Unreleased\n\n"
        "## 0.2.0 - 2026-10-16\n\n### Fixed\n\n- A bug\n\n"
        "## 0.1.0 - 2026-10-01\n\n- Old\n"
    )
    assert section(updated, "0.2.0") == "### Fixed\n\n- A bug\n"
    assert section(updated, "0.1.0") == "- Old\n"
    assert section(updated, "9.9.9") is None


def test_add_section_twice_leaves_the_file_alone() -> None:
    assert add_section(CHANGELOG, "0.1.0", date(2026, 10, 16), "- New\n") == CHANGELOG


def test_add_section_to_the_first_release() -> None:
    first = "# Changelog\n\n## Unreleased\n"
    assert add_section(first, "0.1.0", date(2026, 10, 16), "- New\n") == (
        "# Changelog\n\n## Unreleased\n\n## 0.1.0 - 2026-10-16\n\n- New\n"
    )
