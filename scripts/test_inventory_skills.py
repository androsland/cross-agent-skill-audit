#!/usr/bin/env python3
"""Focused tests for inventory_skills.py."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("inventory_skills.py")
SPEC = importlib.util.spec_from_file_location("inventory_skills", MODULE_PATH)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def skill_record(
    name: str,
    description: str,
    path: str,
    content: str,
    body: str,
    platform_scope: str = "test",
    extra_frontmatter: dict[str, str] | None = None,
    claude_explicit_only: bool = False,
    codex_implicit_invocation: bool | None = None,
    resolved_path: str | None = None,
) -> dict:
    frontmatter = {"name": name, "description": description}
    frontmatter.update(extra_frontmatter or {})
    return {
        "name": name,
        "description": description,
        "when_to_use": "",
        "path": path,
        "resolved_path": resolved_path or path,
        "platform_scope": platform_scope,
        "content_sha256": inventory.sha256(content),
        "body_sha256": inventory.sha256(body),
        "portable_metadata_sha256": inventory.sha256(
            json.dumps(
                {
                    key: value
                    for key, value in frontmatter.items()
                    if key not in inventory.PLATFORM_VARIANT_KEYS
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        ),
        "platform_family": inventory.platform_family(platform_scope),
        "claude_explicit_only": claude_explicit_only,
        "codex_implicit_invocation": codex_implicit_invocation,
        "broken_relative_references": [],
    }


class InventoryTests(unittest.TestCase):
    def test_frontmatter_block_description(self) -> None:
        data, body = inventory.parse_frontmatter(
            "---\nname: example\ndescription: >\n  Audit installed skills\n  without changing them.\n---\nBody\n"
        )
        self.assertEqual(data["name"], "example")
        self.assertEqual(data["description"], "Audit installed skills without changing them.")
        self.assertEqual(body, "Body\n")

    def test_safe_cross_platform_metadata_variant_is_not_collision(self) -> None:
        body = "Shared instructions"
        left = skill_record(
            "example",
            "Same",
            "C:/codex/example/SKILL.md",
            "A",
            body,
            "codex-user",
            codex_implicit_invocation=False,
        )
        right = skill_record(
            "example",
            "Same",
            "C:/claude/example/SKILL.md",
            "B",
            body,
            "claude-user",
            {"disable-model-invocation": "true"},
            claude_explicit_only=True,
        )
        result = inventory.analyze([left, right], inventory.DEFAULT_SIMILARITY)
        self.assertEqual(result["same_name_different_content"], [])
        self.assertEqual(len(result["same_body_platform_metadata_variants"]), 1)

    def test_same_body_behavioral_metadata_difference_is_collision(self) -> None:
        body = "Shared instructions"
        left = skill_record(
            "example", "One", "C:/codex/example/SKILL.md", "A", body, "codex-user"
        )
        right = skill_record(
            "example", "Two", "C:/claude/example/SKILL.md", "B", body, "claude-user"
        )
        result = inventory.analyze([left, right], inventory.DEFAULT_SIMILARITY)
        self.assertEqual(len(result["same_name_different_content"]), 1)
        self.assertEqual(result["same_body_platform_metadata_variants"], [])

    def test_same_body_opposite_invocation_modes_collide(self) -> None:
        body = "Shared instructions"
        left = skill_record(
            "example",
            "Same",
            "C:/codex/example/SKILL.md",
            "A",
            body,
            "codex-user",
            codex_implicit_invocation=True,
        )
        right = skill_record(
            "example",
            "Same",
            "C:/claude/example/SKILL.md",
            "B",
            body,
            "claude-user",
            {"disable-model-invocation": "true"},
            claude_explicit_only=True,
        )
        result = inventory.analyze([left, right], inventory.DEFAULT_SIMILARITY)
        self.assertEqual(len(result["same_name_different_content"]), 1)
        self.assertEqual(result["same_body_platform_metadata_variants"], [])

    def test_different_bodies_with_same_name_collide(self) -> None:
        left = skill_record("example", "One", "C:/one/SKILL.md", "A", "First")
        right = skill_record("example", "Two", "C:/two/SKILL.md", "B", "Second")
        result = inventory.analyze([left, right], inventory.DEFAULT_SIMILARITY)
        self.assertEqual(len(result["same_name_different_content"]), 1)

    def test_missing_relative_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_dir = Path(temporary) / "example"
            skill_dir.mkdir()
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text(
                "---\nname: example\ndescription: Example audit skill.\n---\n[Missing](references/nope.md)\n",
                encoding="utf-8",
            )
            record = inventory.inventory_skill(skill_path, "test", Path(temporary))
            self.assertEqual(
                record["broken_relative_references"],
                [str(Path("references") / "nope.md")],
            )

    def test_default_roots_stop_at_repository_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            repository = home / "work" / "project"
            cwd = repository / "nested"
            cwd.mkdir(parents=True)
            (repository / ".git").mkdir()
            roots = inventory.default_roots(home, cwd)
            paths = [os.path.normcase(str(path)) for _, path in roots]
            self.assertEqual(
                paths.count(os.path.normcase(str(home / ".agents" / "skills"))), 1
            )
            self.assertNotIn(
                os.path.normcase(str(home / "work" / ".agents" / "skills")), paths
            )

    def test_traversal_errors_are_reported(self) -> None:
        warnings: list[str] = []
        with mock.patch.object(inventory.os, "scandir", side_effect=PermissionError("denied")):
            self.assertEqual(list(inventory.find_skill_files(Path("blocked"), warnings)), [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("cannot scan directory", warnings[0])

    def test_exact_copy_hash_uses_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = []
            warnings: list[str] = []
            for dirname, invalid_byte in (("one", b"\xff"), ("two", b"\xfe")):
                skill_dir = root / dirname
                skill_dir.mkdir()
                skill_path = skill_dir / "SKILL.md"
                skill_path.write_bytes(b"---\nname: example\n---\n" + invalid_byte)
                records.append(inventory.inventory_skill(skill_path, "test", root, warnings))
            result = inventory.analyze(records, inventory.DEFAULT_SIMILARITY)
            self.assertEqual(result["exact_copies_at_distinct_realpaths"], [])
            self.assertEqual(len(warnings), 2)

    def test_codex_policy_uses_exact_path_and_allows_inline_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_dir = Path(temporary)
            agents_dir = skill_dir / "agents"
            agents_dir.mkdir()
            config = agents_dir / "openai.yaml"
            config.write_text(
                "interface:\n  allow_implicit_invocation: true\n"
                "policy:\n  allow_implicit_invocation: false # manual-only\n",
                encoding="utf-8",
            )
            self.assertIs(inventory.codex_implicit_policy(skill_dir), False)

            config.write_text(
                "interface:\n  allow_implicit_invocation: false\n",
                encoding="utf-8",
            )
            self.assertIsNone(inventory.codex_implicit_policy(skill_dir))

    def test_claude_policy_uses_top_level_key_and_allows_inline_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill_dir = root / "example"
            skill_dir.mkdir()
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text(
                "---\nname: example\ndisable-model-invocation: true # manual-only\n---\nBody\n",
                encoding="utf-8",
            )
            record = inventory.inventory_skill(skill_path, "claude-user", root)
            self.assertIs(record["claude_explicit_only"], True)

            skill_path.write_text(
                "---\nname: example\nmetadata:\n  disable-model-invocation: true\n---\nBody\n",
                encoding="utf-8",
            )
            record = inventory.inventory_skill(skill_path, "claude-user", root)
            self.assertIs(record["claude_explicit_only"], False)

    def test_positive_analysis_categories(self) -> None:
        shared_left = skill_record(
            "shared-a",
            "Shared",
            "C:/logical-one/SKILL.md",
            "shared-a",
            "One",
            resolved_path="C:/real/SKILL.md",
        )
        shared_right = skill_record(
            "shared-b",
            "Shared",
            "C:/logical-two/SKILL.md",
            "shared-b",
            "Two",
            resolved_path="C:/real/SKILL.md",
        )
        exact_left = skill_record(
            "copy-a", "Copy", "C:/copy-a/SKILL.md", "identical", "One"
        )
        exact_right = skill_record(
            "copy-b", "Copy", "C:/copy-b/SKILL.md", "identical", "Two"
        )
        overlap_left = skill_record(
            "deploy-general",
            "Deploy production website release",
            "C:/deploy-general/SKILL.md",
            "deploy-general",
            "One",
        )
        overlap_right = skill_record(
            "deploy-provider",
            "Deploy production website release provider",
            "C:/deploy-provider/SKILL.md",
            "deploy-provider",
            "Two",
        )
        result = inventory.analyze(
            [
                shared_left,
                shared_right,
                exact_left,
                exact_right,
                overlap_left,
                overlap_right,
            ],
            inventory.DEFAULT_SIMILARITY,
        )
        self.assertEqual(len(result["same_realpath_installations"]), 1)
        self.assertEqual(len(result["exact_copies_at_distinct_realpaths"]), 1)
        self.assertEqual(len(result["trigger_overlap_candidates"]), 1)

    def test_invalid_cli_options_exit_two(self) -> None:
        cases = (
            (["--root", "invalid"], "expected PLATFORM=PATH"),
            (["--similarity", "1.1"], "--similarity must be between 0 and 1"),
            (["--max-skills", "0"], "--max-skills must be positive"),
        )
        for arguments, expected_error in cases:
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [sys.executable, str(MODULE_PATH), *arguments],
                    capture_output=True,
                    check=False,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected_error, result.stderr)


if __name__ == "__main__":
    unittest.main()
