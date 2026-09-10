---
name: skill-audit
description: Audit filesystem-based Codex and Claude Code skills for duplicate installations, name collisions, overlapping triggers, contradictory behavior, missing Markdown-linked files, and portability problems. Use only when explicitly invoked; default to a read-only report.
disable-model-invocation: true
argument-hint: "[optional extra skill roots]"
---

# Cross Agent Skill Audit

Audit the installed skill collection as a system. Do not infer that a same-name directory is redundant until its resolved path, content, platform scope, and behavior have been checked.

## Default: read-only audit

1. Resolve `scripts/inventory_skills.py` relative to this `SKILL.md` and run:

   ```text
   python <resolved-script-path> --format report-json
   ```

   Pass additional roots with `--root platform=path` only when the user names them. Add `--include-plugin-caches` only when cached plugin versions are relevant; cache presence does not prove a plugin is active. The script reads skill metadata and checks references; it does not edit anything or access skill usage logs.
2. Review the inventory in this order:
   - scan warnings and unreadable files;
   - same real path exposed through multiple platform roots;
   - same-name, different-content collisions;
   - exact copies at distinct real paths;
   - heuristic trigger-overlap candidates;
   - missing relative files referenced by Markdown links;
   - platform-specific metadata or instructions.
3. For each plausible trigger or behavioral conflict, read the complete `SKILL.md` files involved. Descriptions and similarity scores are leads, not proof.
4. Test each claimed collision with at least one realistic ambiguous request. State which skill should win and why.
5. Use actual evidence before calling a skill unused. The default scanner deliberately does not inspect conversation logs, so report usage as unknown unless the user supplies appropriate evidence.
6. Return:
   - inventory by Codex, Claude Code, shared, repository, and plugin scope;
   - confirmed conflicts, exact duplicates, and harmless shared installations;
   - high-, medium-, and low-confidence recommendations;
   - exact paths affected by each recommendation;
   - a cleanup plan that preserves rollback.

## Cleanup mode

An audit never changes installed skills. If the user separately asks to apply the cleanup:

1. Show the exact paths and proposed keep, disable, merge, move, or remove action.
2. Explain platform impact and whether a path is a link, shared source, or independent copy.
3. Obtain confirmation immediately before destructive or difficult-to-recover actions.
4. Prefer disabling or moving to a dated quarantine directory over deletion.
5. Never modify bundled/system skills, plugin caches, or shared junction targets as a shortcut.
6. Re-run the inventory afterward and report the observable difference.

## Interpretation rules

- A shared skill exposed in both `.agents/skills` and `.claude/skills` through a junction or symlink is one installation, not a duplicate to remove.
- A same-name, different-content pair is a collision even if the descriptions look similar.
- An exact copied skill may be intentional when platforms cannot share a path; report scope before recommending consolidation.
- Similar descriptions identify candidates only. Confirm overlap from the bodies, invocation policy, and a concrete prompt.
- Missing references can be conditional or generated at runtime. Check the instructions before calling them broken.
- Do not equate installation count with context cost; explicit-only skills may be hidden until invoked.

## Required coverage and limits

This audit must handle at least these unrelated cases:

1. writing skills such as a humanizer and personal-voice skill competing for the same rewrite request;
2. delivery skills such as a general ship workflow and a provider-specific deployment skill overlapping on "push this live."

It must not flag a legitimate shared source linked into both Codex and Claude Code roots as two conflicting copies.

It cannot observe built-in binary skills, cloud/API-uploaded skills, actual historical usage, runtime-generated instructions, relative paths mentioned only in prose or code spans, or non-skill commands/hooks/agents unless those surfaces are separately supplied. Name those blind spots in every report.
