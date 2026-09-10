#!/usr/bin/env python3
"""Read-only inventory for filesystem-based Codex and Claude Code skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


MAX_SKILL_BYTES = 2 * 1024 * 1024
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "vendor", "__pycache__"}
STOP_WORDS = {
    "about", "after", "agent", "agents", "also", "and", "are", "before",
    "claude", "codex", "does", "for", "from", "into", "only", "skill",
    "skills", "that", "the", "their", "this", "use", "user", "when", "with",
}
PLATFORM_VARIANT_KEYS = {
    "argument-hint",
    "disable-model-invocation",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory Codex and Claude Code skills without modifying them."
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="PLATFORM=PATH",
        help="Add a skill root. May be repeated.",
    )
    parser.add_argument(
        "--no-defaults", action="store_true", help="Scan only roots passed with --root."
    )
    parser.add_argument(
        "--include-plugin-caches",
        action="store_true",
        help="Also scan plugin caches; cached versions are not proof that a plugin is active.",
    )
    parser.add_argument(
        "--format", choices=("json", "report-json", "summary"), default="summary"
    )
    parser.add_argument(
        "--similarity",
        type=float,
        default=0.42,
        help="Jaccard threshold for trigger-overlap candidates (default: 0.42).",
    )
    parser.add_argument("--max-skills", type=int, default=3000)
    return parser.parse_args()


def default_roots(home: Path, cwd: Path) -> list[tuple[str, Path]]:
    roots = [
        ("shared-user", home / ".agents" / "skills"),
        ("codex-user-legacy", home / ".codex" / "skills"),
        ("claude-user", home / ".claude" / "skills"),
    ]

    current = cwd.resolve()
    repository_root = current
    while repository_root.parent != repository_root and not (
        repository_root / ".git"
    ).exists():
        repository_root = repository_root.parent
    if not (repository_root / ".git").exists():
        repository_root = current

    while True:
        roots.extend(
            [
                ("repo-shared", current / ".agents" / "skills"),
                ("repo-codex-legacy", current / ".codex" / "skills"),
                ("repo-claude", current / ".claude" / "skills"),
            ]
        )
        if current == repository_root:
            break
        current = current.parent
    return roots


def parse_root(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"invalid --root {value!r}; expected PLATFORM=PATH")
    platform, raw_path = value.split("=", 1)
    if not platform.strip() or not raw_path.strip():
        raise ValueError(f"invalid --root {value!r}; expected PLATFORM=PATH")
    return platform.strip(), Path(raw_path).expanduser()


def unique_roots(roots: Iterable[tuple[str, Path]]) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    seen: set[tuple[str, str]] = set()
    for platform, path in roots:
        absolute = Path(os.path.abspath(path))
        key = (platform, os.path.normcase(str(absolute)))
        if key not in seen:
            seen.add(key)
            result.append((platform, absolute))
    return result


def find_skill_files(root: Path, warnings: list[str] | None = None) -> Iterable[Path]:
    seen_dirs: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            real_key = os.path.normcase(str(directory.resolve()))
        except OSError:
            real_key = os.path.normcase(str(directory.absolute()))
        if real_key in seen_dirs:
            continue
        seen_dirs.add(real_key)

        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            if warnings is not None:
                warnings.append(f"{directory}: cannot scan directory: {error}")
            continue
        for entry in entries:
            try:
                if entry.name == "SKILL.md" and entry.is_file(follow_symlinks=True):
                    yield Path(entry.path)
                elif entry.name not in SKIP_DIRS and entry.is_dir(follow_symlinks=True):
                    pending.append(Path(entry.path))
            except OSError as error:
                if warnings is not None:
                    warnings.append(f"{entry.path}: cannot inspect entry: {error}")


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return str(json.loads(value))
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    normalized = text.replace("\r\n", "\n")
    match = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", normalized, re.S)
    if not match:
        return {}, normalized

    lines = match.group(1).splitlines()
    data: dict[str, str] = {}
    index = 0
    while index < len(lines):
        field = re.match(r"^([A-Za-z0-9_-]+):[ \t]*(.*)$", lines[index])
        if not field:
            index += 1
            continue
        key, value = field.group(1), field.group(2)
        if value in {"|", ">", "|-", ">-", "|+", ">+"}:
            block: list[str] = []
            index += 1
            while index < len(lines) and (not lines[index] or lines[index][0].isspace()):
                block.append(lines[index].strip())
                index += 1
            separator = " " if value.startswith(">") else "\n"
            data[key] = separator.join(block).strip()
            continue
        data[key] = unquote(value)
        index += 1
    return data, normalized[match.end():]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def markdown_relative_links(body: str) -> list[str]:
    links: list[str] = []
    for raw in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", body):
        target = raw.strip().strip("<>").split("#", 1)[0].strip()
        if not target or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
            continue
        if target.startswith("#"):
            continue
        links.append(target.replace("/", os.sep))
    return links


def codex_implicit_policy(skill_dir: Path) -> bool | None:
    config = skill_dir / "agents" / "openai.yaml"
    if not config.is_file():
        return None
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"(?m)^\s*allow_implicit_invocation:\s*(true|false)\s*$", text, re.I)
    return match.group(1).lower() == "true" if match else None


def trigger_tokens(skill: dict[str, Any]) -> set[str]:
    source = f"{skill['description']} {skill['when_to_use']}"
    words = set(re.findall(r"[a-z0-9][a-z0-9-]{2,}", source.lower()))
    return {word for word in words if word not in STOP_WORDS}


def platform_family(platform: str) -> str:
    lowered = platform.lower()
    for family in ("claude", "codex", "shared"):
        if family in lowered:
            return family
    return lowered


def inventory_skill(
    path: Path,
    platform: str,
    root: Path,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    stat = path.stat()
    if stat.st_size > MAX_SKILL_BYTES:
        raise ValueError(f"SKILL.md exceeds {MAX_SKILL_BYTES} bytes")
    content = path.read_bytes()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        if warnings is not None:
            warnings.append(
                f"{path}: invalid UTF-8 at byte {error.start}; metadata decoded with replacement characters"
            )
        text = content.decode("utf-8", errors="replace")
    frontmatter, body = parse_frontmatter(text)
    name = frontmatter.get("name") or path.parent.name
    description = frontmatter.get("description", "")
    when_to_use = frontmatter.get("when_to_use", "")
    claude_explicit = frontmatter.get("disable-model-invocation", "").lower() == "true"
    codex_implicit = codex_implicit_policy(path.parent)

    broken_refs = []
    for link in markdown_relative_links(body):
        candidate = path.parent / link
        if not candidate.exists():
            broken_refs.append(link)

    return {
        "name": name,
        "description": description,
        "when_to_use": when_to_use,
        "platform_scope": platform,
        "root": str(root),
        "path": str(path.absolute()),
        "resolved_path": str(path.resolve()),
        "content_sha256": sha256_bytes(content),
        "body_sha256": sha256(body),
        "portable_metadata_sha256": sha256(
            json.dumps(
                {
                    key: value
                    for key, value in frontmatter.items()
                    if key not in PLATFORM_VARIANT_KEYS
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        ),
        "platform_family": platform_family(platform),
        "bytes": stat.st_size,
        "claude_explicit_only": claude_explicit,
        "codex_implicit_invocation": codex_implicit,
        "broken_relative_references": sorted(set(broken_refs)),
    }


def grouped(skills: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for skill in skills:
        groups[os.path.normcase(str(skill[field]))].append(skill)
    return groups


def compact_skill(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": skill["name"],
        "path": skill["path"],
        "resolved_path": skill["resolved_path"],
        "platform_scope": skill["platform_scope"],
        "content_sha256": skill["content_sha256"],
    }


def analyze(skills: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    same_realpath = []
    for items in grouped(skills, "resolved_path").values():
        logical_paths = {item["path"] for item in items}
        scopes = {item["platform_scope"] for item in items}
        if len(logical_paths) > 1 or len(scopes) > 1:
            same_realpath.append([compact_skill(item) for item in items])

    exact_duplicates = []
    for items in grouped(skills, "content_sha256").values():
        realpaths = {os.path.normcase(item["resolved_path"]) for item in items}
        if len(realpaths) > 1:
            exact_duplicates.append([compact_skill(item) for item in items])

    name_collisions = []
    platform_metadata_variants = []
    name_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for skill in skills:
        name_groups[skill["name"].lower()].append(skill)
    for name, items in name_groups.items():
        realpaths = {os.path.normcase(item["resolved_path"]) for item in items}
        hashes = {item["content_sha256"] for item in items}
        if len(realpaths) > 1 and len(hashes) > 1:
            body_hashes = {item["body_sha256"] for item in items}
            metadata_hashes = {item["portable_metadata_sha256"] for item in items}
            platform_families = {item["platform_family"] for item in items}
            entry = {"name": name, "skills": [compact_skill(i) for i in items]}
            if (
                len(body_hashes) == 1
                and len(metadata_hashes) == 1
                and len(platform_families) > 1
            ):
                platform_metadata_variants.append(entry)
            else:
                name_collisions.append(entry)

    unique_by_realpath: dict[str, dict[str, Any]] = {}
    for skill in skills:
        unique_by_realpath.setdefault(os.path.normcase(skill["resolved_path"]), skill)
    unique = list(unique_by_realpath.values())
    overlap_candidates = []
    token_cache = [trigger_tokens(skill) for skill in unique]
    for left_index, left in enumerate(unique):
        for right_index in range(left_index + 1, len(unique)):
            right = unique[right_index]
            if left["name"].lower() == right["name"].lower():
                continue
            left_tokens, right_tokens = token_cache[left_index], token_cache[right_index]
            intersection = left_tokens & right_tokens
            union = left_tokens | right_tokens
            if len(intersection) < 3 or not union:
                continue
            score = len(intersection) / len(union)
            if score >= threshold:
                overlap_candidates.append(
                    {
                        "left": compact_skill(left),
                        "right": compact_skill(right),
                        "score": round(score, 3),
                        "shared_terms": sorted(intersection),
                    }
                )
    overlap_candidates.sort(key=lambda item: item["score"], reverse=True)

    broken_refs = [
        {
            "name": skill["name"],
            "path": skill["path"],
                "references": skill["broken_relative_references"],
        }
        for skill in skills
        if skill["broken_relative_references"]
    ]

    return {
        "same_realpath_installations": same_realpath,
        "exact_copies_at_distinct_realpaths": exact_duplicates,
        "same_name_different_content": name_collisions,
        "same_body_platform_metadata_variants": platform_metadata_variants,
        "trigger_overlap_candidates": overlap_candidates,
        "missing_markdown_references": broken_refs,
    }


def render_summary(report: dict[str, Any]) -> str:
    analysis = report["analysis"]
    lines = [
        "Cross-agent skill inventory (read-only)",
        f"Skills found: {len(report['skills'])}",
        f"Roots scanned: {len(report['roots_scanned'])}",
        f"Warnings: {len(report['warnings'])}",
        f"Shared real paths: {len(analysis['same_realpath_installations'])}",
        f"Exact copies at distinct real paths: {len(analysis['exact_copies_at_distinct_realpaths'])}",
        f"Same-name different-content collisions: {len(analysis['same_name_different_content'])}",
        f"Same-body platform metadata variants: {len(analysis['same_body_platform_metadata_variants'])}",
        f"Trigger-overlap candidates: {len(analysis['trigger_overlap_candidates'])}",
        f"Skills with missing Markdown references: {len(analysis['missing_markdown_references'])}",
    ]
    if report["warnings"]:
        lines.append("\nWarnings:")
        lines.extend(f"- {warning}" for warning in report["warnings"])
    return "\n".join(lines)


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    unique_realpaths: set[str] = set()
    for skill in report["skills"]:
        counts[skill["platform_scope"]] += 1
        unique_realpaths.add(os.path.normcase(skill["resolved_path"]))
    return {
        "schema_version": report["schema_version"],
        "mode": report["mode"],
        "cwd": report["cwd"],
        "roots_scanned": report["roots_scanned"],
        "roots_missing": report["roots_missing"],
        "warnings": report["warnings"],
        "inventory_counts_by_scope": dict(sorted(counts.items())),
        "inventory_entries": len(report["skills"]),
        "unique_resolved_skill_files": len(unique_realpaths),
        "analysis": report["analysis"],
        "blind_spots": report["blind_spots"],
    }


def main() -> int:
    args = parse_args()
    if not 0 <= args.similarity <= 1:
        print("--similarity must be between 0 and 1", file=sys.stderr)
        return 2
    if args.max_skills < 1:
        print("--max-skills must be positive", file=sys.stderr)
        return 2

    home = Path.home()
    cwd = Path.cwd()
    roots: list[tuple[str, Path]] = [] if args.no_defaults else default_roots(home, cwd)
    if args.include_plugin_caches:
        roots.extend(
            [
                ("codex-plugin-cache", home / ".codex" / "plugins" / "cache"),
                ("claude-plugin-cache", home / ".claude" / "plugins" / "cache"),
            ]
        )
    try:
        roots.extend(parse_root(value) for value in args.root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    roots = unique_roots(roots)

    skills: list[dict[str, Any]] = []
    warnings: list[str] = []
    roots_scanned: list[dict[str, str]] = []
    roots_missing: list[dict[str, str]] = []
    for platform, root in roots:
        if not root.is_dir():
            roots_missing.append({"platform": platform, "path": str(root)})
            continue
        roots_scanned.append({"platform": platform, "path": str(root)})
        try:
            for skill_path in find_skill_files(root, warnings):
                if len(skills) >= args.max_skills:
                    warnings.append(f"stopped after --max-skills={args.max_skills}")
                    break
                try:
                    skills.append(inventory_skill(skill_path, platform, root, warnings))
                except (OSError, ValueError) as error:
                    warnings.append(f"{skill_path}: {error}")
        except OSError as error:
            warnings.append(f"{root}: {error}")
        if len(skills) >= args.max_skills:
            break

    skills.sort(key=lambda item: (item["name"].lower(), item["path"].lower()))
    report = {
        "schema_version": 1,
        "mode": "read-only",
        "cwd": str(cwd),
        "roots_scanned": roots_scanned,
        "roots_missing": roots_missing,
        "warnings": warnings,
        "skills": skills,
        "analysis": analyze(skills, args.similarity),
        "blind_spots": [
            "built-in or binary-provided skills",
            "cloud/API-uploaded skills",
            "historical usage unless separately supplied",
            "runtime-generated instructions",
            "commands, hooks, and agents outside SKILL.md",
            "whether a skill found only in a plugin cache is currently active",
            "behavioral conflicts not visible in metadata until bodies are reviewed",
            "relative file references expressed only as prose or backticked paths",
        ],
    }
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.format == "report-json":
        print(json.dumps(compact_report(report), indent=2, ensure_ascii=False))
    else:
        print(render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
