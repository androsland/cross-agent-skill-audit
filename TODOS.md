# Deferred work

## Optimize trigger-overlap candidate generation

- [ ] Replace the bounded all-pairs comparison with a token-to-skill inverted index.
- Context: `analyze()` currently compares every distinct resolved skill pair. The
  `--max-skills` cap bounds the work, but a 3,000-skill scan can still perform about
  4.5 million pair comparisons.
- Acceptance: candidate generation compares only pairs sharing at least three trigger
  tokens while preserving the current Jaccard threshold and deterministic ordering.
- Non-goal: do not turn heuristic overlap candidates into confirmed behavioral
  conflicts; full skill-body review and a realistic ambiguous prompt remain required.
