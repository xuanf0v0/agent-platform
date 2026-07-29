# US Children's Swim Aid / Toddler Swim Vest Listing Audit

Use this reference for Amazon US listings described as toddler swim vests, arm floaties, puddle-style jumpers, buoyancy aids, or kids life jackets. These are safety-sensitive children's products: copy clarity and classification consistency take priority over keyword density.

## 1. Parent/child resolution first

- A submitted parent ASIN can redirect to a selected child. Record all three separately when available: submitted parent ASIN, selected child ASIN, and child style/configuration.
- Search visibility is child-level. A sibling ranking much higher than the selected child is a variation-level signal, not proof that the family lacks keyword relevance.
- Keep child-only structure such as crotch strap, removable arm bands, pattern, age/weight range, and color out of parent-safe fields unless every child shares it.
- Ratings/review counts on public pages may be variation-aggregated; label them accordingly.

## 2. Safety and fact-consistency gate

Before drafting, reconcile every safety-critical fact across Title, bullets, Product Overview, images, A+, video, packaging/manual, and compliance documents:

| Fact | Typical conflict to catch | Required action |
|---|---|---|
| Product classification | `Life Jacket` in title vs `Buoyancy Aid` in details | Confirm approved classification/label before wording |
| Weight range | `22–66 lb` in title/images vs `70 lb` detail-field limit | Stop and obtain one verified range |
| Age range | `2–6 Years` vs `infant` wording | Remove unsupported audience expansion |
| Materials | `Nylon` detail field vs `Nylon + EPE Foam + Lycra` image | Verify complete BOM/material composition |
| Included structure | Crotch strap, shoulder harness, detachable arm bands | Confirm per child ASIN; do not inherit across siblings |
| Supervision/warnings | Present in one bullet but absent in images/A+ | Preserve required warning consistently |
| Approval/certification | `life jacket`, `safety device`, USCG/CPSC implications | Route to compliance/human; never infer approval from competitor wording |

For US children's products, CPC/testing/label requirements and any flotation-device approval claims require official-document and compliance review. Shared KB summaries are orientation only, not final legal proof.

## 3. High-risk wording audit

Treat these as P0/P1 until substantiated:

- `life jacket` when the product is only identified as a buoyancy/swim aid
- `maximum flotation`, `unparalleled support`, `float effortlessly`
- `keeps your child's head above water`, `prevents slipping/flipping/scrapes`
- `safe`, `secure`, `highest quality`, or `long-lasting` used as absolute proof
- language that implies the product replaces adult supervision

Prefer verified, qualified mechanism statements only after approval, e.g. describing adjustable straps, buckle operation, foam construction, fit range, or intended supervised swim practice. Do not draft the safer replacement until Stage 2 approval.

`Puddle Jumper` may be used as brand-like language in the category; flag it for trademark/IP screening rather than assuming it is safely generic.

## 4. Public-Amazon keyword/rank ladder

When SellerSprite/SIF volume is unavailable, do not call competitor wording “high search volume.” Use public results only as location- and time-sensitive rank/relevance evidence.

Probe from broad to exact intent:

1. `toddler swim vest`
2. `toddler swim vest 22-66 lbs`
3. `toddler floaties 22-66 lbs`
4. Product-specific structure terms such as `toddler swim vest crotch strap`

Record selected child, sibling children, and 2–3 direct competitors separately. Compare visible price, rating/review count, badges, title front-load, and organic position. A selected child at #20 while a sibling is #3 can indicate price/style/offer/history differences; it does not justify stuffing more keywords into the parent title.

## 5. Copy audit priorities

- Verify title length and exact-token repetition programmatically.
- Separate A9 coverage from readability: these listings often already cover `toddler swim vest`, `toddler floaties`, weight range, and audience terms but remain difficult to scan.
- Audit bullets for total mobile burden, one-intent-per-bullet structure, native US grammar, and duplicated safety claims.
- Common grammar/trust failures include plural/agreement errors, age lists such as `2 3 4 5 6 Years Old`, awkward phrases such as `3 style lovely cartoon pattern`, and misspelling `floatation` where `flotation` is intended.
- Apply the same universal repair patterns used in the paste-ready optimizer: fix dangling title tails (`… Harness Arm`), truncated Item Highlights openings, product-vs-person subject errors (`This toddler is…`, `The kids provides…`), and age/weight stuffing before SEO polish.
- Bullet role split for swim aids: (1) weight/age fit, (2) harness/arm-wing structure, (3) supervised swim practice, (4) allowed scenes only if manual-supported, (5) not a life-saving device + adult supervision.
- Mechanism vs performance: `shoulder harness with arm wings` is structural; `helps the vest stay in position`, `supportive buoyancy`, and `natural arm movement` need packaging/manual/test evidence or must be softened/removed.
- COSMO/Rufus questions to make answerable: What is the verified weight/age range? Is it a life jacket or swim aid? Does this child include a crotch strap? What are the materials? How does the buckle open? Where may it be used? Is adult supervision required?

## 6. Image-stack audit

- Size/fit imagery should reconcile chest circumference, arm opening/circumference, age, and weight with detail fields.
- Buckle imagery should explain the mechanism without implying it is childproof or foolproof.
- Material imagery must match the verified BOM and avoid unsupported durability/safety claims.
- Lifestyle scenes must show truthful supervised use and avoid implying unsupervised protection.
- Distinguish current-child images from preloaded variation assets. Scraping every `hiRes` URL from all page scripts can pull sibling variation images that are not in the selected child's visible stack. Use the visible thumbnail DOM/current-ASIN image set as the source of truth, then map only those images to high-resolution URLs.

## 7. Stage-1 output requirements

Before rewriting, return:

1. Parent/selected-child identification
2. Safety/fact conflict table
3. Current title and bullet length checks
4. Keyword/intent coverage with volume gap disclosed
5. Public rank comparison separating siblings
6. Image-by-image diagnosis of only the selected child's visible stack
7. Compliance escalation list
8. Approval gate

After approval, produce parent-safe and child-specific fields separately, plus A+/image/Q&A plans and a human compliance checklist. Never modify the live listing directly.