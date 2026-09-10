#!/usr/bin/env python3
"""Focused tests for inventory_skills.py."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("inventory_skills.py")
SPEC = importlib.util.spec_from_file_location("inventory_skills", MODULE_PATH)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def skill_record(name: str, description: str, path: str, content: str, body: str) -> dict:
    return {
        "name": name,
        "description": description,
        "when_to_use": "",
        "path": path,
        "resolved_path": path,
        "platform_scope": "test",
        "content_sha256": inventory.sha256(content),
        "body_sha256": inventory.sha256(body),
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

    def test_same_body_metadata_variant_is_not_collision(self) -> None:
        body = "Shared instructions"
        left = skill_record("example", "One", "C:/codex/example/SKILL.md", "A", body)
        right = skill_record("example", "Two", "C:/claude/example/SKILL.md", "B", body)
        result = inventory.analyze([left, right], 0.42)
        self.assertEqual(result["same_name_different_content"], [])
        self.assertEqual(len(result["same_body_platform_metadata_variants"]), 1)

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


if __name__ == "__main__":
    unittest.main()
