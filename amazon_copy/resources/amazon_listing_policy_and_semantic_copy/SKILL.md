---
name: amazon-listing-policy-and-semantic-copy
description: Create, audit, or optimize Amazon listings under the post-July-27-2026 title and Item Highlights rules. Use for titles, Item Highlights, bullets, descriptions, backend Search Terms, attributes, images, A+, variations, COSMO, Rufus or Alexa for Shopping, keyword allocation, claims, compliance reviews, and listing quality scoring.
---

# Amazon Listing Policy and Semantic Copy

## Overview

This is the policy and evidence gate shared by `listing-create` and `listing-optimize`. Load it before drafting, scoring, or recommending changes to any Amazon listing. It converts verified product facts and buyer intent into concise, answerable copy without keyword stuffing, invented research, or unsupported claims.

Default to the rules that apply **from July 27, 2026 onward**. For non-media categories, draft the Title at no more than 75 characters and Item Highlights at no more than 125 characters. Do not offer a legacy 200-character title unless the user explicitly asks for historical comparison.

Read:

- `references/amazon-policy-baseline-2026.md` for current rules and official sources.
- `references/cosmo-alexa-shopping-boundaries.md` when COSMO, Rufus, Alexa for Shopping, semantic SEO, Q&A, or intent optimization is involved.
- `references/source-material-reconciliation.md` when applying the four internal SOP files supplied in July 2026.

Run `scripts/lint_listing.py` on final copy whenever a JSON draft can be created.

## Source-of-Truth Order

Resolve conflicts in this order:

1. Current official Seller Central help for the exact marketplace, product type, and category; the category template or live field validator wins.
2. Dated Amazon News/Announcements and official Amazon guidance.
3. Applicable law, product-safety rules, and substantiation evidence.
4. Verified product brief, packaging, manual, certificates, test reports, and approved brand facts.
5. First-party seller data such as SQP, Brand Analytics, Search Query data, and verified experiments.
6. SellerSprite/SIF or public-Amazon observations, labeled with marketplace and time window.
7. Competitor structure, reviews, Q&A, forums, and internal SOPs as research inputs only.
8. Hypotheses. Clearly label them and never present them as Amazon policy or measured fact.

If a lower source conflicts with a higher source, ignore the lower rule. Do not use an internal quota merely because it is more specific.

## Required Evidence Gate

Before final copy, build a compact fact ledger:

| Fact or claim | Value | Source | Scope | Status |
|---|---|---|---|---|
| Brand/product type |  | brief/PDP | parent or child | verified/missing/conflict |
| Size, quantity, material |  | manual/package | per unit or pack | verified/missing/conflict |
| Compatibility/use |  | manual/test | exact models/scenarios | verified/missing/conflict |
| Performance/safety claim |  | test/certificate | conditions/limits | verified/missing/conflict |

Rules:

- Never invent dimensions, count, material, compatibility, origin, certification, warranty, performance, medical benefit, audience share, purchase-motive share, or review-theme percentage.
- If data does not exist, use `待补` or `未验证`; do not create a plausible number.
- Competitor copy proves only what the competitor claims, not what this product can claim.
- Convert a feature to a benefit only when the mechanism is defensible. Use qualified wording such as `designed to`, `helps`, or `suitable for` when appropriate.
- For regulated or safety-sensitive categories, stop at a draft and mark the claim for human compliance review.

## Post-July-27-2026 Field Rules

### Title

For all non-media categories:

- Maximum 75 characters including spaces.
- Keep only the minimum product identity: brand when required, product type/core phrase, and the most decision-critical verified specification or differentiator.
- Continue to exclude restricted characters `! $ ? _ { } ^ ¬ ¦` unless an official exception applies to the brand.
- Do not repeat the same word more than twice; articles, conjunctions, and prepositions are exceptions.
- Exclude price, shipping, promotion, ranking, subjective hype, calls to action, competitor brands, seller name, and unsupported absolutes.
- Preserve the strongest relevant phrase only when it remains grammatical. Do not chain synonyms.
- Parent titles must be parent-safe. Child titles may include only that child's verified variation values.

For media, retrieve the current category rule rather than applying 75 characters automatically.

### Item Highlights

- Maximum 125 characters including spaces.
- Treat it as searchable, customer-visible supporting copy.
- Use one coherent phrase or short sentence for verified materials, recommended uses, compatibility, comparison-relevant details, or the highest-value information displaced from the short Title.
- Add new decision information. Do not paraphrase the Title, compress Bullet 1, or join keywords with commas.
- If the field is not enabled for the target category/account, label the draft `Item Highlights 建议稿`; do not silently substitute it into a different field.

### Bullets

- Use all five available bullets when the category exposes five and verified information supports them.
- Begin with a capital letter; use clear sentence fragments. End punctuation is optional.
- Give each bullet one decision job: primary outcome, proof/differentiator, fit or compatibility, use/care/setup, and risk/expectation management.
- Include features, materials, dimensions, and use cases only when verified.
- Do not include price, promotion, shipping, external contact details, emojis, decorative characters, refund guarantees, review requests, or unsupported claims.
- No fixed keyword count, root count, or target stuffing density. Clarity and relevance outrank quota completion.

### Backend Search Terms

- Stay within 250 UTF-8 bytes.
- Use lowercase, spaces, and no unnecessary punctuation.
- Add relevant synonyms, abbreviations, alternate names, local-language variants, and residual buyer vocabulary.
- Do not repeat the brand or words already used in the Title when avoidable.
- Never include competitor brands, ASINs, promotional/temporary statements, profanity, or false product attributes.
- Build this field after visible copy is final, then remove duplicate tokens and re-count bytes.

### Attributes, Images, Description, A+, and Video

- Complete all required and useful recommended attributes accurately. Structured attributes are evidence for search, browse, comparison, and shopping-assistant answers; missing or incorrect values can suppress or misclassify a listing.
- Main image: pure white background, product only, no text/logo/watermark, and product fills at least 85% of the frame. Use at least 1000 pixels on the longest side for zoom; use accepted formats.
- Secondary images and video should prove scale, included parts, setup, texture, use, and limitations. Do not imply accessories are included when they are not.
- Description and A+ should answer objections, explain use/care, and differentiate verified configurations. Treat A+ primarily as conversion and return-reduction content; do not make an absolute indexing claim.
- Compare only the brand's own products in A+ comparison modules unless current policy explicitly permits another use.

## Semantic Intent Model

Build semantics from evidence, not from filler:

`buyer task/question → scenario → verified attribute → mechanism/proof → qualified benefit → best field`

For each important intent, record:

| Buyer question or task | Verified product answer | Proof | Field | Missing evidence |
|---|---|---|---|---|

Use query and review data to discover language. Do not infer percentages from a list of themes. Use labels such as `observed`, `measured`, `user-provided`, or `hypothesis`.

Good semantic coverage answers:

- What is it and what is included?
- Who or what is it for?
- Where and when is it used?
- What size/material/model is it?
- How is it installed, used, cleaned, stored, or maintained?
- What limitation or compatibility condition prevents a wrong purchase?
- How does this verified configuration differ from another product from the same brand?

## Creation Workflow

Use for a new listing:

1. Confirm marketplace, product type/category, media status, parent/child scope, and language.
2. Create the fact ledger and block all unsupported claims.
3. Gather keyword and intent evidence. Rank only with measured data; otherwise use relevance tiers without invented volume labels.
4. Map fields before writing:
   - Title: identity and critical fit/spec.
   - Item Highlights: strongest complementary decision information.
   - Bullets: five distinct buyer decisions.
   - Attributes: complete structured facts.
   - Description/A+: objections, use, proof, and own-product comparison.
   - Search Terms: relevant residual vocabulary.
5. Draft native marketplace language, not literal translation.
6. Run policy, claim, parent/child, cross-field duplication, character, and byte checks.
7. Deliver copy plus evidence map, counts, and unresolved items.

Do not force approval gates when the user asks for direct output. Ask only when a missing fact would materially change or falsify the copy.

## Optimization Workflow

Use for an existing listing:

1. Snapshot the current ASIN, selected child, marketplace, visible fields, attributes, offer state, images, and source time.
2. Separate observable evidence from unavailable backend metrics.
3. Locate the actual gap: suppression/indexing, exposure, search-result CTR, detail-page CVR, or offer/fulfillment.
4. Audit policy first, then fact consistency, then semantic answerability, then keyword allocation and readability.
5. Compare only direct substitutes for copy conclusions. Adjacent products may inform language, not prove equivalence.
6. Recommend the smallest defensible change. Preserve a working phrase/rank signal unless evidence supports replacing it.
7. For title migration, produce the post-July-27 format directly: Title ≤75 plus Item Highlights ≤125, then rebuild backend Search Terms.
8. Keep live edits as recommendations requiring the established human/operations approval path.

## Reviews, Q&A, Variations, and AI Content

- Never fabricate reviews, Q&A, customer research, or user-percentage tables.
- A neutral review request may use Amazon's approved `Request a Review` route. Never request only positive reviews, divert negative feedback, offer incentives/refunds, ask for removal/change, or manipulate competitor reviews.
- Do not create variation relationships to aggregate reviews. From the 2026 review-sharing update, only minor non-functional differences remain eligible for shared reviews; functional differences can have reviews attributed to the specific child.
- Q&A topics may be proposed from real buyer questions, but every answer must use verified facts and must not be spam-posted.
- Amazon AI suggestions and shopping-assistant outputs are not trusted product evidence. Review every generated title, Item Highlight, bullet, attribute, or answer for accuracy; monitor Review Listings Changes regularly.

## Output Contract

For a final copy task, return:

1. Upload-ready marketplace-language fields.
2. Chinese reference translation when useful.
3. Character counts for Title and Item Highlights; UTF-8 byte count for Search Terms.
4. Compact keyword/intent allocation map.
5. Claim evidence and unresolved `待补` items.
6. Policy audit with `PASS`, `WARN`, or `BLOCK`.

Do not bold keywords in upload-ready copy. If an annotated review draft is useful, keep it separate.

## Verification Checklist

- [ ] Target marketplace, category/product type, media status, and parent/child scope are explicit.
- [ ] Title is at most 75 characters for a post-July-27 non-media listing.
- [ ] Item Highlights are at most 125 characters and add non-duplicative value.
- [ ] Title repetition and restricted-character rules pass.
- [ ] Five bullets are clear, distinct, and free of promotion, emojis, and refund guarantees.
- [ ] Search Terms are relevant, de-duplicated, brand/ASIN-free, and at most 250 UTF-8 bytes.
- [ ] Every specification and performance claim maps to evidence.
- [ ] Attributes, visible copy, images, and variation values do not contradict one another.
- [ ] No invented percentages, keyword quotas, ranking guarantees, or algorithm claims remain.
- [ ] Alexa for Shopping/COSMO guidance is framed as answerability and relevance, not a guaranteed ranking formula.
- [ ] Review and variation recommendations do not manipulate review systems.
- [ ] Final copy passed `scripts/lint_listing.py`, or any manual-check limitation is disclosed.

