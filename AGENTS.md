# Repository instructions

- Preserve read-only default behavior. Audit does not imply cleanup authorization.
- Never print environment values, conversation logs, or skill bodies from the scanner.
- Treat description overlap as a candidate until complete skill bodies and a realistic prompt confirm it.
- Distinguish links, identical copies, same-body platform variants, and same-name behavioral collisions.
- Keep the scanner compatible with Python 3.10+ and standard-library only.
- Keep `SKILL.md` and `platforms/claude/SKILL.claude.md` bodies identical; only supported platform frontmatter may differ.
- Run `python scripts/test_inventory_skills.py` and `python tests/test_package.py` before proposing a change.
- Do not add AI attribution to commits, issues, pull requests, or releases.
