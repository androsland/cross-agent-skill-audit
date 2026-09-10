#!/usr/bin/env python3
"""Focused tests for inventory_skills.py."""

from __future__ import annotations

import importlib.util
import json
import os
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
) -> dict:
    frontmatter = {"name": name, "description": description}
    frontmatter.update(extra_frontmatter or {})
    return {
        "name": name,
        "description": description,
        "when_to_use": "",
        "path": path,
        "resolved_path": path,
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
            "example", "Same", "C:/codex/example/SKILL.md", "A", body, "codex-user"
        )
        right = skill_record(
            "example",
            "Same",
            "C:/claude/example/SKILL.md",
            "B",
            body,
            "claude-user",
            {"disable-model-invocation": "true"},
        )
        result = inventory.analyze([left, right], 0.42)
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
        result = inventory.analyze([left, right], 0.42)
        self.assertEqual(len(result["same_name_different_content"]), 1)
        self.assertEqual(result["same_body_platform_metadata_variants"], [])

    def test_different_bodies_with_same_name_collide(self) -> None:
        left = skill_record("example", "One", "C:/one/SKILL.md", "A", "First")
        right = skill_record("example", "Two", "C:/two/SKILL.md", "B", "Second")
        result = inventory.analyze([left, right], 0.42)
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
            result = inventory.analyze(records, 0.42)
            self.assertEqual(result["exact_copies_at_distinct_realpaths"], [])
            self.assertEqual(len(warnings), 2)


if __name__ == "__main__":
    unittest.main()
