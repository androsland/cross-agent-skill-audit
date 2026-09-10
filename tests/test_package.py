#!/usr/bin/env python3
"""Validate package layout and platform invocation policy."""

from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def boolean_assignments(text: str, key: str, indent: int = 0) -> list[str]:
    return re.findall(
        rf"(?mi)^{' ' * indent}{re.escape(key)}:[ \\t]*(true|false)[ \\t]*(?:#.*)?$",
        text,
    )


def mapping_blocks(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    for index, line in enumerate(lines):
        if not re.fullmatch(rf"{re.escape(key)}:[ \\t]*(?:#.*)?", line):
            continue
        block: list[str] = []
        for child in lines[index + 1 :]:
            if child and not child[0].isspace():
                break
            block.append(child)
        blocks.append("\n".join(block))
    return blocks


def split_skill(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not match:
        raise AssertionError(f"invalid frontmatter in {path}")
    return match.group(1), match.group(2)


class PackageTests(unittest.TestCase):
    def test_platform_bodies_match(self) -> None:
        _, codex_body = split_skill(ROOT / "SKILL.md")
        _, claude_body = split_skill(ROOT / "platforms" / "claude" / "SKILL.claude.md")
        self.assertEqual(codex_body, claude_body)

    def test_invocation_policies_are_explicit_only(self) -> None:
        codex_frontmatter, _ = split_skill(ROOT / "SKILL.md")
        claude_frontmatter, _ = split_skill(
            ROOT / "platforms" / "claude" / "SKILL.claude.md"
        )
        openai_config = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        policy_blocks = mapping_blocks(openai_config, "policy")
        self.assertEqual(
            boolean_assignments(codex_frontmatter, "disable-model-invocation"), []
        )
        self.assertEqual(
            boolean_assignments(claude_frontmatter, "disable-model-invocation"),
            ["true"],
        )
        self.assertEqual(
            boolean_assignments(openai_config, "allow_implicit_invocation", indent=2),
            ["false"],
        )
        self.assertEqual(len(policy_blocks), 1)
        self.assertEqual(
            boolean_assignments(
                policy_blocks[0], "allow_implicit_invocation", indent=2
            ),
            ["false"],
        )

    def test_policy_checks_reject_nested_keys(self) -> None:
        self.assertEqual(
            boolean_assignments(
                "policy:\n  nested:\n    allow_implicit_invocation: false\n",
                "allow_implicit_invocation",
                indent=2,
            ),
            [],
        )
        self.assertEqual(
            boolean_assignments(
                "metadata:\n  disable-model-invocation: true\n",
                "disable-model-invocation",
            ),
            [],
        )

    def test_scanner_runs_without_writing_to_fixture(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "example-skill"
        before = sorted(path.relative_to(fixture) for path in fixture.rglob("*"))
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "inventory_skills.py"),
                "--no-defaults",
                "--root",
                f"test={fixture}",
                "--format",
                "report-json",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        after = sorted(path.relative_to(fixture) for path in fixture.rglob("*"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, after)
        self.assertIn('"mode": "read-only"', result.stdout)


if __name__ == "__main__":
    unittest.main()
