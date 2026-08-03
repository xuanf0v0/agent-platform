# Open-Source Adaptations

This repository adapts bounded concepts from the following MIT-licensed projects. The upstream
projects are not runtime dependencies and their agent frameworks are not vendored. Local Amazon
policy, evidence authorization, deterministic postflight checks, and API contracts remain
authoritative.

## E-commerce Visual Copywriting Skill

- Upstream: `https://github.com/feichanggege/ecommerce-visual-copywriting-skill`
- License: MIT; archived at `docs/licenses/ecommerce-visual-copywriting-skill-LICENSE.txt`
- Upstream commit: `38736d1ca30ee3b96d7015a16594e6c351ec3610`
- Provenance captured: 2026-08-03 from the repository's `HEAD`; the archived license was retrieved
  from that exact commit.
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
- License: MIT; archived at `docs/licenses/marketingskills-LICENSE.txt`
- Upstream commit: `7868cb9251fad80a73d26e488a5ad5f6c4a9f335`
- Provenance captured: 2026-08-03 from the repository's `HEAD`; the archived license was retrieved
  from that exact commit.
- Local adaptation: seven read-only editorial sweep scores mapped from the existing ten-dimension
  diagnosis and postflight reports. No upstream prose, agent framework, or automatic rewrite path
  is included.
- Runtime boundary: observations are redacted, best-effort, non-user-visible, and never participate
  in generation, candidate selection, quality gates, or rewriting.

## License Handling

Both exact upstream commits contain the MIT License. Their complete copyright and permission
notices are archived unchanged under `docs/licenses/`; retain those files with this adaptation.
