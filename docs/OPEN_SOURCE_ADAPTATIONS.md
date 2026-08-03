# Open-Source Adaptations

This repository adapts bounded concepts from the following MIT-licensed projects. The upstream
projects are not runtime dependencies and their agent frameworks are not vendored. Local Amazon
policy, evidence authorization, deterministic postflight checks, and API contracts remain
authoritative.

## E-commerce Visual Copywriting Skill

- Upstream: `https://github.com/feichanggege/ecommerce-visual-copywriting-skill`
- License: MIT
- Upstream commit: `UNRESOLVED`
- Retrieval status: the exact commit query was blocked by the execution environment's network
  approval service on 2026-08-03; do not replace this marker with a branch name or date.
- Local adaptation: Amazon-only Campaign Style Lock, verified
  `Feature -> Advantage -> Buyer Benefit -> Evidence`, storyboard approval gate, main image plus
  seven secondary-image task allocation, and five independent visual reviews. China-marketplace
  rules were not imported.
- Runtime boundary: guidance is appended only for an explicit image/visual request or an
  affirmative reply to an immediately preceding visual handoff. Ordinary listing prompts remain
  byte-for-byte unchanged.

## Marketing Skills Copy Editing

- Upstream: `https://github.com/coreyhaines31/marketingskills`
- Upstream resource: `skills/copy-editing/SKILL.md`
- License: MIT
- Upstream commit: `UNRESOLVED`
- Retrieval status: the exact commit query was blocked by the execution environment's network
  approval service on 2026-08-03; do not replace this marker with a branch name or date.
- Local adaptation: seven read-only editorial sweep scores mapped from the existing ten-dimension
  diagnosis and postflight reports. No upstream prose, agent framework, or automatic rewrite path
  is included.
- Runtime boundary: observations are redacted, best-effort, non-user-visible, and never participate
  in generation, candidate selection, quality gates, or rewriting.

## License Handling

Both upstream repositories advertise the MIT License. Before release, resolve each exact commit and
archive the corresponding upstream `LICENSE` text and copyright notice alongside this document.
The unresolved markers intentionally block claiming provenance that was not verified.
