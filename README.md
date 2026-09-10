# Cross-Agent Skill Audit

A read-only inventory and analysis workflow for filesystem-based Codex and Claude
Code skills.

It finds same-name collisions, exact copies, overlapping trigger candidates,
broken relative references, explicit-versus-automatic invocation differences,
and platform portability problems. Metadata similarity is treated as a lead; the
agent must read the relevant skill bodies before confirming a behavioral conflict.

## Safety model

The default audit never edits skills and never reads conversation logs. Cleanup is
a separate mode requiring exact path-level proposals and confirmation before any
destructive action. Disabling or dated quarantine is preferred over deletion.

## Install

### Codex

```powershell
git clone https://github.com/androsland/cross-agent-skill-audit.git "$HOME\.agents\skills\skill-audit"
```

Invoke it with `$skill-audit`.

### Claude Code

Place the repository in `~/.claude/skills/skill-audit`. To keep it manual-only,
either select `user-invocable-only` from Claude Code's `/skills` menu, or install
`platforms/claude/SKILL.claude.md` as the directory's `SKILL.md`.

Invoke it with `/skill-audit`.

## Direct scanner use

The scanner uses Python 3.10+ and the standard library only:

```text
python scripts/inventory_skills.py --format summary
python scripts/inventory_skills.py --format report-json
```

Plugin caches are excluded by default because cache presence does not establish
that a plugin is active. Include them deliberately:

```text
python scripts/inventory_skills.py --include-plugin-caches --format report-json
```

The complete per-skill inventory is available with `--format json`. The compact
report format is intended for agent review without flooding the context window.

## Intended coverage and limits

The audit must handle unrelated collision shapes such as humanizer versus
personal-voice rewriting skills and a general ship workflow versus a
provider-specific deployment workflow. A platform-specific copy or shared link
with the same behavior must not be called a conflict solely because it appears in
two roots.

The audit cannot observe built-in binary skills, cloud/API-uploaded skills, actual
historical usage, runtime-generated instructions, or non-skill commands, hooks,
and agents unless those surfaces are separately supplied.

## Inspiration

This is an independent implementation informed by the public work in
[scottholdren/skill-audit](https://github.com/scottholdren/skill-audit) and
[steipete/agent-scripts skill-cleaner](https://github.com/steipete/agent-scripts/blob/main/skills/skill-cleaner/SKILL.md).
No source code was copied from those projects.

## License

MIT
