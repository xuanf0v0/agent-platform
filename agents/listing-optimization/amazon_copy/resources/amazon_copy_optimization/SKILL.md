---
name: amazon-copy-optimization
description: Use when the user replies “文案优化” or asks to analyze/optimize Amazon listing copy for an ASIN. Run a data-backed copy audit first, using ASIN + competitor/keyword tools, then ask for user approval before producing optimized title, Item Highlights, bullets, or other copy.
version: 1.4.4
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [amazon, listing, copywriting, seo, cosmo, a9, title, bullets]
    related_skills: [amazon-listing-optimization, ocr-and-documents]
---

# Amazon Copy Optimization

## Overview

Use this skill for **post-launch Amazon listing copy analysis and optimization**, especially when the user simply says **“文案优化”** after providing or planning to provide an ASIN. The workflow is deliberately two-stage:

1. **Analyze and score first** — use Amazon/SellerSprite/SIF data and the user’s SOP/rules to evaluate the current copy.
2. **Optimize only after approval** — ask whether the user recognizes/accepts the analysis. Only after they approve should you produce optimized copy.

Do not directly edit live listings. Title, bullets, Item Highlights, A+, backend terms, price, variants, and image changes are all recommendations requiring human/operations approval.

## Mandatory shared policy gate

Load `amazon-listing-policy-and-semantic-copy` before this skill. Its post-July-27-2026 policy, evidence hierarchy, Alexa for Shopping terminology, review/variation integrity rules, and deterministic checks override conflicting internal SOP guidance in this file.

## When to Use

Load this skill when:

- The user replies **“文案优化”**.
- The user provides an Amazon ASIN and asks for listing copy analysis, title optimization, bullet optimization, SEO analysis, or文案打分.
- The user asks to evaluate copy quality using Amazon rules, A9 SEO, COSMO SEO, grammar, readability, selling points, localization, professionalism, emotional appeal, and call-to-action.
- The user asks for optimized Amazon title/bullets after a copy audit.

Do **not** use this as the primary skill for pure image analysis/design; use the image workflow or image-specific skill/SOP instead.

## Required Inputs

Ask for missing inputs only when they are not inferable from tools.

Minimum viable input:

- Marketplace, usually `US`
- Own ASIN

Useful optional inputs:

- Competitor ASINs
- Current title and bullets, if not live or not retrievable
- Product specs/manual
- Evidence-backed keywords, roots, synonyms, and buyer questions
- Target audience or positioning

If only ASIN + marketplace are provided, proceed with MCP/tool analysis rather than asking the user to paste content.

## Data Sources and Tool Order

Use available read-only tools. Label every number with source and time window.

1. **Listing content and baseline**
   - SellerSprite ASIN detail: title, brand, price, rating, ratings/reviews, variation count, category if available.
   - Public Amazon page/browser extraction when needed: title, bullets, details, visible images/A+ cues.

2. **Keyword and traffic signals**
   - SIF `market_get_asin_keyword_signals` for ASIN-level traffic keywords, natural vs ad ranks, contribution changes, keyword health.
   - SIF `ops_get_listing_traffic_overview` for natural/ad traffic mix when relevant.
   - SellerSprite keyword miner/research for search volume, purchases, purchase rate, title density, products, PPC bid, monopoly click rate.

3. **Competition and demand**
   - SIF `market_get_keyword_competition` for top competitor ASINs and market structure for the main keywords.
   - SIF `market_get_keyword_demand` or keyword history for lifecycle/seasonality if demand timing matters.
   - SellerSprite ASIN detail for competitor titles/ratings/prices.
   - If Amazon search results are blocked but the own PDP loads, use PDP recommendation/related-product carousels as a public fallback: extract `/dp/<ASIN>` links whose titles match the same product form, deduplicate ASINs, then open 2–3 direct comparables separately. Prefer same configuration and mechanism before adjacent products.
   - If the interactive browser is challenged but raw public PDP HTML is retrievable, follow `references/amazon-public-pdp-and-autocomplete-fallback.md` to extract current title/bullets/details/A+/images and use Amazon autocomplete as query-language evidence. Do not convert autocomplete suggestions into search-volume or rank claims.
   - Treat repeated wording across public competitor titles as **market-language evidence only**, not proof of search volume, traffic tier, or ranking potential. Cap the SEO conclusion accordingly and state that SellerSprite/SIF keyword evidence is still required.

4. **Rules and SOP**
   - Apply current official policy before the user-provided Amazon copy SOP or COSMO/Rufus docs.
   - For post-July-27-2026 work, non-media Title `≤75 characters` and Item Highlights `≤125 characters` are official general requirements. Retrieve the current rule for media and obey any stricter marketplace/category validator.
   - When the official Seller Central help page is login-gated or cannot be verified, state that limitation and audit only the requirements supported by the retrieved source. Do not label an internal SOP or skill snapshot as “Amazon's latest official rule.”
   - Before claiming that a title violates the “same word more than twice” rule, normalize case/punctuation and count exact word tokens programmatically or in the page DOM. Never eyeball repetitions in a long title.

## Two-Stage Workflow

### Stage 1 — Audit and Score

Do this before writing optimized copy.

**Chinese repeated-ASIN audit pattern:** when the user asks only `给出 <ASIN> 的标题、五点、search term 的优化建议`, treat it as a request for **audit + optimization directions**, not automatically as final rewritten copy. Provide diagnosis, strategy, scoring, and a confirmation question. **Explicit-output override:** if the user supplies the current title, required keywords, competitor, parent/child details, Title/Highlight character targets, and explicitly asks to `输出` the optimized Title/Item Highlights/Search Terms, that request itself authorizes Stage 2 for that ASIN. Gather evidence, then deliver upload-ready fields without asking for a redundant approval turn.

**Ongoing-session continuation override:** once the user has approved the field format in the current conversation—such as no brand, Title `≤75`, Item Highlights `≤125`, dimensions/spec allocation, capitalization, or keyword-only title strategy—and then provides another ASIN or a batch with `写标题和商品亮点`, treat that as authorization to continue Stage 2 under the established format. Carry explicit field-style corrections forward through that batch: if the user removes the brand to free title space and asks to embed more relevant keyword phrases, subsequent titles should remain brandless and use the recovered space for natural, verified product-language phrases rather than reverting to `Brand + Product Type`. Likewise, if the user requests Item Highlights with meaningful words capitalized and ordinary connectors lowercase, preserve that style on later ASINs. Still retrieve and verify every new ASIN's facts, parent/child mapping, and SKU differences, but do not interrupt the batch with another generic approval gate unless a material ambiguity changes the output (for example, parent-wide vs child-specific copy, conflicting dimensions, or an unverified safety claim). Product-specific exceptions do not silently become global rules: carry forward only the formatting conventions clearly established for the ongoing batch.

For COSMO and Alexa for Shopping (formerly Rufus), user-intent keyword library, title/bullet SOP, and advertising-funnel linkage learned from the user's uploaded internal docs, consult `references/cosmo-rufus-copy-rules.md` only after the shared policy skill; never apply its fixed counts, unverified algorithm claims, or invented proportions.

For UK cellophane / hamper / treat-bag products, also consult `references/uk-cellophane-hamper-copy.md` for keyword families, localization choices, and compliance pitfalls.

For UK bakery packaging products (cake boxes, cookie boxes, brownie boxes, pastry/treat boxes, bakery gift boxes), consult `references/uk-bakery-packaging-copy.md` for UK keyword families, multi-size variation handling, title/bullet templates, image checklist, and claim guardrails.

For US natural scallop-shell craft products, consult `references/us-natural-scallop-shell-copy.md` only for **product-class** constraints: parent/child handling, broad-to-exact public rank probes, recurring market-language phrases, food-contact/claim guardrails, image/package traps, and natural-variation wording. **Field architecture (Title / Item Highlights / five one-intent bullets / backend allocation) is global** — follow the paste-ready `listing_optimizer` prompt few-shot for every product type, including this class.

For US children's swim aids, toddler swim vests, arm floaties, and puddle-style jumpers, consult `references/us-childrens-swim-aid-listing-audit.md` before scoring or drafting. It contains the safety/classification consistency gate, parent-child rank separation, claim-risk checks, public query ladder, and selected-child image-stack verification.

When the submitted ASIN is a parent, redirects to a child, or contains pack/size variations, consult `references/parent-child-variation-copy.md` before scoring or drafting. Build the parent-child configuration matrix first and distinguish parent-safe fields from child-specific copy.

For **any** specialized-fact BLOCK cascade (dimensions, BOM counts, thickness, performance, fit ranges), consult `references/structured-fact-authorization-and-cascade-dedupe.md` before rewriting. Merge findings by `fact_key`, fill a SKU structured authorization table, resolve shared accessory-count ambiguity, degrade unconfirmed precision, and edit only fields that cite unauthorized values. Old listing copy and competitor listings never authorize product facts.

Do this before writing optimized copy.

1. **Confirm scope**
   - State ASIN, marketplace, product, and available data sources.
   - If only the ASIN is known, say that competitor/keyword data was pulled from tools.

2. **Extract current copy**
   - Title, bullets, brand, key product attributes, rating/review count, price if available.
   - Check for obvious trust-breaking errors: wrong brand, wrong product type, inconsistent size/material/color, spelling mistakes, impossible claims.
   - Audit structured attributes as well as visible prose: `Model Name`, `Set Name`, `Included Components`, unit count, product dimensions, and package weight. A field calling a shells-only or refill-only product a `kit` is a package-identity risk even if the title avoids the word. For natural products, distinguish representative catalog dimensions from approximate per-piece size and classify user-provided weight as net, packaged, or shipping weight before using it.
   - Audit A+ semantically, not as a yes/no presence flag. Distinguish product-specific objection handling, setup/use guidance, comparisons, and specification proof from generic brand-story/navigation modules. An A+ block can exist technically while contributing little to CVR or Alexa for Shopping answerability. Also run a cross-category contamination check: if the A+ promotes unrelated product classes (for example, office organizers on a natural-shell PDP), flag it as a trust/CVR mismatch even when A+ is technically present.
   - Treat Item Highlights as a separate field from the public PDP bullets. If Amazon's public page does not expose the field reliably, report it as unavailable/not scoreable rather than inferring that it is blank or silently treating bullets as Item Highlights. Ask for a Seller Central export or user-provided field only when the missing current value materially affects Stage 2.
   - When review volume is very low or review bodies cannot be reliably extracted, do not manufacture review-mined objections; use competitor/common buyer-question evidence and mark own-review evidence as insufficient.
   - Completion criterion: current title and five bullets are available or data gap is explicitly stated.

3. **Build keyword and purchase-intent map**
   - List the key ASIN traffic keywords and important market keywords.
   - Mark whether each keyword is covered exactly, partially, or missing in title/bullets.
   - Translate keywords into **TOP user purchase intents**: use cases, buyer tasks, concerns, materials/specs, scenarios, and objections.
   - Completion criterion: at least 10 meaningful keywords/intents are classified, or the tool data gap is stated.

3A. **Use same-word rank gaps before scoring SEO**
   - Never give an 8–10 SEO score from title/bullet structure alone when own and competitor keyword tools are available. Pull actual own-ASIN and competitor data first.
   - For each priority term, compare own vs direct competitor vs strong keyword benchmark on traffic share, organic position, ad position, searches, and purchase-rate/relevance signals using the same marketplace and month.
   - Distinguish direct product-form competitors from adjacent SEO leaders. Adjacent products can establish a keyword/rank ceiling but cannot prove equivalent value, dimensions, or conversion.
   - Treat strong ad position plus weak organic position as an ad-to-organic sedimentation gap. Strengthen relevant listing semantics and conversion support; do not diagnose it as advertising alone.
   - SellerSprite safeguard: a zero result from `traffic_keyword_stat` is not enough to declare `no keywords`. Call detailed `traffic_keyword` and inspect populated `data.items` before classifying the ASIN as cold-start/no-rank.
   - A data-backed score must show: `own traffic concentration + natural/ad ranks → competitor same-word gaps → keyword allocation → length/repetition/claim verification`.
   - If SellerSprite/SIF volume is unavailable, never label a phrase “high search volume” from competitor wording alone. Use Amazon organic-result snapshots only as **rank/relevance evidence**, label repeated competitor wording as **market-language evidence**, and explicitly state that monthly volume/ABA rank remains unverified.
   - For public-search fallback, test a query ladder from broad to exact intent (for example `product` → `attribute + product` → `product + use` → `attribute + product + use`). Record own child, sibling variants, and 2–3 direct competitors separately. A sibling ranking much higher than the target child is a variation-level signal, not proof that the target title alone is defective.
   - Preserve the strongest relevant phrase intact in the title when the exact phrase has materially better organic placement than its broader components; do not split it merely to put size before the product phrase.
   - For US wood/acoustic wall panels, follow `references/wood-wall-panel-keyword-gap-seo.md`.

3B. **Separate Title, Item Highlights, and backend Search Terms roles**
   - When the user supplies keyword tiers such as `core conversion long-tail`, `high-traffic broad term`, and `term with organic rank`, preserve that hierarchy explicitly in the audit. Label the hierarchy as **user-provided keyword evidence** unless SellerSprite/SIF/SQP supplies numeric search volume, traffic contribution, or rank.
   - Detect nested phrases before allocating title space. If a verified conversion phrase such as `fan shaped desk file organizer` already contains the broad phrase `desk file organizer`, count both as covered and do not repeat the broad phrase separately. Preserve the strongest exact long-tail intact when relevant, then use remaining space for a distinct organic-rank phrase only if the title remains natural rather than becoming a synonym chain.
   - For title-only requests, keep Stage 1 tightly scoped: current title and child/parent identity, verified product facts, keyword-tier coverage, new-rule risks, proposed title skeleton, and approval question. Do not expand into a full bullet/A+/ten-dimension listing audit unless the user requested a complete copy review.
   - Scenario words supplied by the user (`school`, `office`, `classroom`, etc.) are secondary to brand, product identity, verified count/size, and high-priority keyword phrases in a short title. Move excess scenarios to Item Highlights or bullets instead of turning the title into a room/use-case list.
   - The user prefers minimal semantic repetition between Title and Item Highlights. Title should spend its budget on identity: brand, product type, pack/count, size/model, and one defining attribute. Item Highlights should spend its budget on complementary material, functional benefits, design/ease advantages, a few representative scenarios, objections, or purchase-intent terms.
   - Before finalizing, normalize case/punctuation and compare meaningful tokens across the two visible fields. Ignore stopwords such as `for`, `and`, and `the`, but remove repeated product/specification phrases unless repetition is necessary for clarity or a verified indexing reason.
   - Build backend Search Terms only after the Title and Item Highlights are fixed. Create a candidate-root pool from the supplied keyword list, direct-competitor title/bullets, and relevant Amazon SERP wording; then subtract roots already covered in the visible fields instead of repeating full phrases such as `pen organizer for desk` or `desk organizer`.
   - Prefer useful new roots and combinable synonyms: if the title already supplies `pen`, `organizer`, and `desk`, the backend can add roots such as `pencil`, `holder`, `stationery`, or `caddy` rather than restating the same long-tail phrase. Explain this allocation when the user explicitly requests omitted keywords.
   - Never import competitor brands, ASINs, promotional language, or competitor-only features (`non-slip`, `fully assembled`, load limits, etc.) into backend terms without independent product verification. Separate market-language evidence from product-fact claims.
   - Produce upload-ready Search Terms as lowercase, space-separated tokens with no punctuation or duplicate words, and verify UTF-8 byte length at ≤250 bytes. Avoid child-only colors/sizes in a family-shared field unless the draft is explicitly mapped to one child.
   - When asked to maximize field limits, approach the requested limit with useful information rather than filler. Prefer 73–75 meaningful title characters over an awkward exact-75 title, keep Item Highlights natural even if it finishes below its cap, and stop Search Terms below 250 bytes rather than adding weak broad terms.
   - Show character/byte counts and, when useful, a compact field-role or overlap table so the user can verify that each field contributes new information.

3C. **Resolve parent vs child and differentiate related ASINs before drafting**
   - A supplied ASIN may redirect to a default child while actually being a parent. Inspect the landing URL, `parentAsin`, variation map, selected child, pack count, and size before drafting.
   - **Related-ASIN differentiation gate:** when optimizing multiple products from the same class or variation family, retrieve the fields finalized earlier in the session and build a compact contrast matrix covering count, dimensions, form factor, mechanism, included parts, and primary purchase intent. Do not reuse the same title or Item Highlights template and merely substitute a count, color, or size.
   - Lead each SKU with its verified structural or use-case distinction. For example, a compact 4-compartment organizer can lead with `Magazine File Holder` and space-saving storage, while a wider 5-slot Plus model can lead with `Desk File Organizer`, its verified width, and easier binder/folder access. Keep the core keyword family covered, but vary phrase order and field emphasis only when supported by real product differences.
   - Semantic differentiation never justifies inventing features. If no meaningful SKU difference is verified, say so and keep copy consistent rather than forcing artificial uniqueness.
   - Produce a generic parent title without child-only count/size, plus child-specific title/Item Highlights when the requested ASIN is a parent. Never copy the selected child’s `10 PCS`, dimensions, or mixed-size configuration into the parent field or sibling variants.
   - If bullets are shared across the family, either write family-safe bullets or explicitly label the draft as child-specific. Do not silently publish child-specific facts as parent-wide copy.

3B. **Handle parent ASINs and variation-family evidence explicitly**
   - Before auditing copy, determine whether the supplied ASIN is a parent or a saleable child. Amazon may redirect a parent URL to a default child while retaining the parent ASIN in twister/page data.
   - Inspect variation/twister data (`parentAsin`, selected `data-asin`, pack/size/color labels) and report the supplied parent ASIN and selected child ASIN separately.
   - Build a compact variation matrix when pack, size, or color changes the purchase decision. Label price, rating, review count, title, and bullets as child-level or variation-shared; never silently attribute the default child's values to the parent.
   - Search visibility is normally child-level. If multiple siblings appear for the same query, record their positions separately and describe this as family exposure plus sibling distribution—not as one parent rank and not automatically as cannibalization.
   - A parent URL resolving to a child does not prove that the parent copy is wrong. Diagnose title/copy issues only after separating variation mechanics, child relevance, 2026 review attribution/sharing eligibility, and query intent.
   - For Stage 2, keep child-only pack/size/color in child titles; do not insert one child's attributes into a parent title. If the user wants a family-wide rewrite, retrieve each materially different child first.
   - When SellerSprite/SIF is unavailable, public Amazon result pages may support a location- and time-sensitive visibility snapshot. Label it as a snapshot rather than persistent organic rank, do not infer search volume/traffic tier, and cap the SEO conclusion.

3D. **Audit keyword embedding quantity without quotas**
   - Trigger this audit when the user asks how many keywords were embedded, whether the listing has enough keywords, or whether backend terms are being used efficiently.
   - Run `scripts/audit_keyword_embedding.py` against the finalized listing JSON and the evidence-backed target phrase list. Report three separate numbers rather than one inflated total:
     1. **Exact contiguous phrase coverage** by field.
     2. **Root/token-set coverage** across visible fields plus backend Search Terms.
     3. **Backend incremental-token ratio** after subtracting every token already present in Title, Item Highlights, bullets, and description.
   - Normalize case and punctuation. Reconcile conservative singular/plural forms for root coverage, but keep exact-phrase reporting literal.
   - Detect nested phrases. For example, one placement of `wedding welcome sign stand` can mechanically match `wedding welcome sign`, `welcome sign stand`, `welcome sign`, and `sign stand`; disclose those nested hits but do not call them five independent keyword placements.
   - Do not treat a low exact-phrase count as an automatic defect when every measured high-priority phrase has complete, natural root coverage. Conversely, do not call distributed roots an exact phrase or claim guaranteed indexing/rank.
   - Label which target phrases have SellerSprite/SIF/SQP evidence and which are relevance-only candidates. Give a separate coverage rate for measured keywords when both groups are present.
   - If backend Search Terms mostly repeat visible-copy tokens, rebuild them for incremental synonyms, alternate product names, buyer tasks, and secondary scenarios. Never add weak roots merely to hit a fixed count or 250-byte ceiling.
   - Recommend the smallest defensible field change: preserve a working Title phrase/rank signal, add at most one important uncovered exact phrase to Item Highlights or a bullet when it remains natural, then regenerate Search Terms.

4. **Evaluate quality dimensions**
   Score the listing copy out of 10 for each dimension:
   - Compliance
   - A9 SEO: keyword/root coverage and search relevance
   - COSMO semantic coverage: buyer tasks, contexts, scenarios, objections, and evidence-backed questions; no fixed TOP20 quota
   - Grammar/spelling
   - Readability
   - Selling-point completeness
   - Localization/native US expression
   - Professionalism/technical accuracy
   - Emotional appeal/pain-point resonance
   - Call-to-action/purchase motivation without promotional violations

5. **Output Stage 1 in tables**
   Use Chinese output by default unless user asks otherwise.
   Required structure:
   - Diagnosis summary
   - Current listing baseline table
   - Keyword/intent coverage table
   - Competitor/title benchmark table when available
   - Score table with reasons
   - Key deduction points and risk priorities
   - Final question: **“请确认：是否认可以上文案分析和打分？认可后我再输出优化建议/新版文案。”**

Do not provide optimized title/bullets in Stage 1 unless the user already approved a prior audit.

### Stage 2 — Optimization After User Approval

Run after the user says they approve/认可/继续/可以优化, **or** when their request explicitly asks for upload-ready optimized fields and provides the necessary constraints (current copy, required keywords, competitor, variation scope, and character targets). Do not add a redundant approval gate in the latter case.

1. **Apply the verified category rule plus the requested title format**
   1. **Apply the verified category rule plus the requested title format**
      - For post-July-27-2026 non-media listings, produce a title ≤75 characters including spaces and Item Highlights ≤125 characters. Retrieve the current rule for media and obey any stricter marketplace/category validator.
      - Title role: product identification, not keyword stuffing.
      - Preferred title structure: `Brand + Product Type + Key Attribute + Size/Pack/Model`.
      - For mixed-component kits, validate what the total count actually counts. Do not phrase a `33 Piece Set` containing 30 cedar pieces plus 3 fabric bags as `33 Pack Cedar Rings and Balls`; either state the exact component breakdown or distinguish the main-product count from included accessories.
      - Avoid word repetition more than twice, promotional content, subjective claims, decorative symbols, and restricted phrases.
      - **Keyword-only title override:** when the user explicitly says the title should contain only embedded product keywords and that all specifications belong in Item Highlights, override the normal `Brand + Product + Attribute + Spec` structure. Omit brand, dimensions, count, color, material, and feature claims from the title; use 3–4 natural, non-redundant product-language phrases within the requested cap. Move the verified count, dimensions, color, material, structure, accessories, and representative scenarios into Item Highlights. Do not apply this exception silently to other listings—the user must request it.
      - **Brandless keyword-dense title continuation:** when the user corrects an ongoing US short-field batch with `标题不用加品牌名，标题中可以多埋一些关键词`, carry that format through later ASINs in the same sequence without asking again. Omit the brand, retain purchase-critical child facts such as tier/count/size/color where useful, and spend the freed characters on 2–3 distinct natural keyword phrases rather than reordered duplicates. Keep the exact-word repetition ceiling and the active character cap. This is a session/batch formatting convention, not a universal catalog rule; do not silently apply it in unrelated future work unless the user has established the same preference there.
      - **Explicit must-include title facts override:** when the user names exact verified facts that must appear in the title—such as `30 PCS`, `15 Colors`, and `9.3 x 4.5 Inches`—those facts override the default field-allocation preference. Preserve every requested fact verbatim or in an equivalent native-US form, keep the title within the active cap, then regenerate Item Highlights so they add material, benefit, storage objects, and scenarios rather than repeating the same count, color, or dimensions. This override is SKU-specific and must not be carried silently to unrelated products.
      - **Differentiate related ASINs:** before drafting for a sibling or closely related product, compare the previous/family title and Item Highlights. Do not reuse the same sentence frame with only the compartment count, size, or color swapped. Give each SKU a distinct leading keyword family and field structure, based on its actual form or positioning, while retaining relevant indexing roots. If the user says two ASINs look too similar, rewrite both field roles rather than merely replacing one noun.

   2. **Use Item Highlights**
      - Produce Item Highlights ≤125 characters.
      - **Default dimension allocation for this user's short-field workflow:** omit dimensions from Item Highlights unless the user explicitly asks for them there. Put purchase-critical dimensions in the child title or structured specification fields, then spend the Highlight budget on material, structure, buyer benefit, storage objects, and 2–3 representative scenarios. If the user says `商品亮点不需要尺寸` or asks to delete dimensions from a batch, propagate that correction to every requested ASIN rather than fixing only one.
      - **Capitalization style:** capitalize the opening word and meaningful product/feature words, while keeping ordinary connectors such as `with`, `for`, `and`, `at`, `or`, `in`, `a`, and `the` lowercase unless they begin a phrase. Do not convert every word to uppercase-initial Title Case after a request for `首字母大写`; preserve native-looking connector capitalization. Example shape: `Metal Mesh File Organizer with Drawer for Paper, Notes and Office Supplies at Home or School`.
      - **Carry explicit Highlight capitalization through the active batch:** once the user asks for `除介词外，首字母大写`, use the above meaningful-word capitalization for subsequent Item Highlights in that ongoing sequence. Always count after capitalization/punctuation changes. If a requested Highlight exceeds 125 characters, preserve the core keyword phrase, verified structural differentiator, and explicitly requested scenarios first; shorten or remove the lowest-priority stored-object noun before deleting a defining feature or replacing it with an ambiguous term. Never shorten `label panels` to `labels` when the latter could imply that physical labels are included.
      - **User-supplied wording becomes the active style exemplar:** if the user replies with a revised Item Highlight phrase, preserve its wording and capitalization as the preferred draft for that SKU unless a factual, compliance, grammar, or character-limit issue requires a change. Run count/compliance checks and report them; do not re-add dimensions, colors, adjectives, articles, or features the user intentionally removed, and do not silently convert the phrase to full Title Case.
      - Write one concise, coherent product phrase or sentence fragment. Use commas only where they improve natural flow; never turn the field into Search Terms with punctuation, and never compress Bullet 1 into a full explanatory sentence.
      - **Run a keyword-first allocation gate before writing prose.** Start from the user's must-keep/core keyword list and mark which exact phrases are already covered by the Title. Item Highlights must naturally carry the highest-priority uncovered core phrase or high-value synonym before spending characters on descriptive attributes.
      - Include at least one important core keyword or high-value synonym **naturally inside the phrase**. Item Highlights must not become either a keyword-free benefit sentence or a comma-joined synonym list.
      - Do not let low-search descriptive details dominate the field. Attributes such as `reinforced steel frame`, `nonslip pads`, `easy access`, or generic durability language belong only after core keyword coverage is secured and only when they add conversion value. If space is tight, prioritize a complementary phrase such as `mesh desk organizer`, `letter tray`, or another verified keyword family over narrated construction details.
      - Make Item Highlights complement the title instead of mechanically repeating its full identity, count, size, or component list. Example allocation: if the Title covers `paper organizer for desk` and `sliding paper trays`, the Highlight should naturally add `mesh desk organizer` and `letter trays`; it should not merely describe the frame and pads.
      - Check **feature-level semantic overlap**, not only repeated tokens. If the title already says `sliding paper trays`, do not paraphrase the same mechanism in Item Highlights as `pullout tiers`, `easy-access trays`, or another synonym. Spend the Highlight on genuinely new information such as material, handle, storage objects, exact component counts, or scenarios.
      - Prefer the shortest accurate construction. Write `with handle` when `carry handle` adds no verified distinction; do not pad a basic feature with `carry`, `convenient`, `easy-access`, or similar filler merely to use more characters. A natural Highlight below the cap is better than a padded near-125-character version.
      - Balance four elements when verified: `naturally embedded core keyword + product advantage/structure + buyer benefit + 2–3 representative use cases`. The field must answer both `what is it?` and `why/where is it useful?`.
      - Prefer connective phrasing such as `with`, `featuring`, `for easy access`, or `for office supplies...` so the text reads as one native unit. Reject drafts shaped like `desk organizer, pencil holder, pen holder, metal mesh...` even when every token is relevant.
      - Do not spend most of the field on a mechanical list of rooms or use cases; equally, do not write a feature-only explanatory sentence that reads like Bullet 1. Keep scenarios secondary but present.
      - For short-title work, distribute exact phrases and synonyms across title and Item Highlights rather than stuffing every variant into the title. When all component tokens are already indexed, do not repeat an entire long-tail phrase merely for adjacency.
      - After changing Item Highlights, regenerate backend Search Terms: remove words newly covered by title/Highlights and reuse the byte budget for relevant missing synonyms, item types, buyer tasks, and secondary scenarios.
      - **Pack-count compression:** if a child title is already at the character cap and a `2 Pack`/`6 Pack` label must be added, preserve the defining high-intent mechanism and core product phrase; move a secondary modifier to Item Highlights or backend terms. Example: keep `Expandable`, move `Adjustable`. Never solve the count problem by dropping the product's defining mechanism.
      - **Per-unit clarity:** in multi-pack Highlights, prefix a per-item specification with `Each` when omission could imply that the stated divider/accessory/capacity count is the total for the whole pack.
      - **Semantic-safety override for must-keep keywords:** do not force a user-supplied phrase into visible copy when it changes the product identity or creates a misleading reading (for example, `magnetic folders` for a magnetic file holder). Allocate the accurate phrases to Title/Highlights and place only the missing relevant root in backend terms, explaining cross-field token composition.
      - Treat Item Highlights as searchable and visible with title/search/detail context.
      - For the end-to-end US short-title + Item Highlights + backend Search Terms workflow, use `references/us-short-title-highlight-search-terms.md` and `references/short-title-highlight-search-term-allocation.md`. For worked office-organizer examples covering natural Highlights, pack-count compression, per-unit clarity, and semantic-safe keyword allocation, consult `references/us-short-field-office-organizer-examples.md`.

3. **Rewrite bullets**
   - One core intent per bullet.
   - Keep bullets concise and mobile-readable; avoid bloated 250–350 character bullets unless the category/user explicitly wants long bullets.
   - Use **short, scannable bullet subheadings**, normally 2–4 words (for example, `Metal Mesh Frame` or `Easy Assembly`). Do not turn the subheading into a long keyword string. Put remaining SEO terms naturally in the body.
   - When the user asks for keywords in bullets, assign one primary keyword family to each bullet and avoid repeating the same exact phrase mechanically across headings and bodies.
   - Use native US phrasing.
   - Convert specifications into benefits without inventing facts.
   - Reconcile user corrections immediately across all affected fields. For example, if the product includes printed instructions but no video, remove every video reference instead of preserving it from the old listing or competitor copy.
   - Use qualified claims: `helps protect`, `helps deter`, `designed for`, `supports`, `suitable for` instead of absolute claims like `predator proof`, `rust proof`, `guaranteed`, `blocks all`.
   - Maintain technical accuracy for gauge, dimensions, material, coating, mesh opening, compatibility, and use cases.
   - For US metal magazine/file-holder products, consult `references/us-metal-magazine-file-holder-copy.md` for competitor-language handling, keyword allocation, compact subheadings, and backend Search Terms.

3A. **Run a product-fact gate before finalizing Stage 2**
   - Separate facts verified by the ASIN detail/user materials from claims merely present in the old copy or a competitor listing.
   - Never borrow competitor dimensions, capacity, load limits, materials, stability features, installation details, or compatibility claims.
   - If conversion-critical facts are missing (dimensions, per-tier clearance, capacity, load, connection/anti-slip structure, included parts), still produce a conservative draft using only verified facts, then add a human confirmation checklist.
   - Mark conditional phrases such as `trays can be used separately` when they came only from the current copy and require physical confirmation before upload.
   - Prefer deleting weak unsupported filler (`sturdy`, `reduces dust`, `high quality`) over replacing it with another unverified benefit.

3B. **Separate copy quality from listing performance advantages**
   - A competitor may rank and convert better despite poor grammar because of listing age, rating/review volume, A+, video, variations, badges, price, or traffic breadth.
   - Do not treat the best-performing competitor copy as a writing model by default. Diagnose which advantages come from copy and which come from non-copy assets.
   - When only one competitor is supplied, proceed with it, label the comparison limitation, and do not invent additional comparables.
   - Use own-ASIN traffic contribution to prioritize title terms; use competitor keyword breadth and natural ranks to find missing roots. Avoid promoting broad or ambiguous paid terms into the title solely because they have high search volume.

4. **Map copy to A9/COSMO**
   - Provide a keyword allocation table: title, Item Highlights, Bullet 1–5, A+/images/Q&A suggestions.
   - Explain why high-intent terms moved from title to Item Highlights/bullets under the new title rule.

5. **Output Stage 2**
   Required sections:
   - Optimization strategy table
   - New title + Chinese translation
   - Item Highlights + Chinese translation
   - Five bullets + Chinese translation
   - Keyword/intent coverage comparison
   - Human approval checklist
   - 2–4 week validation metrics

   When the user requests three short-title variants, a bullet-planning table, per-bullet character/word counts, compliance/overlap checks, and a final upload-only bullet block, follow `templates/us-full-listing-optimization-output.md` instead of improvising the structure.

## Amazon Title Rules: Verification Hierarchy

Apply this post-July-27-2026 hierarchy:

1. Retrieve the current official rule for the ASIN's exact product type/category when accessible.
2. Apply the official general non-media limits: **Title ≤75 characters** and searchable **Item Highlights ≤125 characters**.
3. Retrieve the current media rule and any stricter Product Type/category constraint when applicable.
4. If a live category field rejects otherwise compliant copy, treat the validator as the active stricter rule and disclose the difference.
5. When the short-title/latest-format request is triggered, put brand + product identity + verified count/size/key attribute in the title, move secondary materials/use cases to Item Highlights (`≤125 characters`, one coherent phrase with a naturally embedded core keyword), and programmatically verify character count and exact-token repetition before responding.
6. If the exact official Product Type rule is retrievable and conflicts with the internal format, follow the official mandatory rule and explain the difference.

Regardless of title length format:

- The title must clearly and concisely identify the product.
- Do not include promotional phrases such as `free shipping` or `100% quality guaranteed`.
- Do not use prohibited/decorative special characters; avoid `!`, `$`, `?`, `_`, `{`, `}`, `^`, `¬`, `¦`, and excessive `~`, `#`, `<`, `>`, `*` unless used in a legitimate identifier/measurement context.
- Verify repeated-word compliance by normalizing case and punctuation and counting exact tokens; do not estimate from visual scanning.
- Do not use subjective phrases like `Hot Item` or `Best Seller`.
- Do not use all caps.
- Use numerals for numbers.
- Put size/color variation details in child ASIN titles, not parent titles.

## Scoring Rubric

| Dimension | 9–10 | 6–8 | ≤5 |
|---|---|---|---|
| Compliance | No rule issues, claims qualified | Minor risk or unclear claim | Wrong brand, prohibited terms, absolute/high-risk claims |
| A9 SEO | Core and high-intent keywords naturally covered | Big terms covered but long tails weak | Core terms missing or stuffed unreadably |
| COSMO SEO | Buyer tasks, contexts, scenarios, objections covered | Some use cases listed, shallow context | Only specs/keywords, little intent context |
| Grammar/spelling | Native, clean, consistent | Understandable with awkward phrasing | Errors reduce trust |
| Readability | Concise, scannable, mobile-friendly | Some long or redundant sentences | Cluttered, hard to scan |
| Selling points | Benefits aligned to purchase motives | Specs present but benefits underdeveloped | Key differentiators missing |
| Localization | Reads like US marketplace copy | Mild translation/template feel | Obvious machine-translation tone |
| Professionalism | Accurate technical language | Some vague claims | Inaccurate or unverified technical claims |
| Emotional appeal | Pain points and peace-of-mind clear | Some generic reassurance | Flat feature list only |
| CTA/purchase motivation | Natural task-completion motivation | Safe but weak | Hard-sell or absent motivation |

## Maximum Character Utilization Requests

When the user asks to `最大化使用字符限制`, `use the full limit`, or otherwise wants dense upload-ready copy:

1. **Maximize naturally, not mechanically.** Fill each field close to the requested/internal cap. If the user explicitly reiterates that they want maximum utilization, actively generate and count several natural alternatives rather than stopping with large unused capacity (for example, do not leave a title at 65/75 when a clear 75/75 version exists). A grammatically correct final period may close a one-character gap, but never add weak adjectives, redundant synonyms, awkward trailing tokens, or misleading use cases solely to hit the cap. A clean 73–74/75 title remains better than an unnatural 75/75 title.
2. **Use the active format targets.** For non-media listings, use Title ≤75 characters and Item Highlights ≤125 characters. Give bullets only the verified decision information they need—there is no 200–300 character target. Backend Search Terms stay ≤250 UTF-8 bytes.
3. **Carry the density preference through an ongoing batch.** Once the user asks to maximize field capacity in the current listing-optimization sequence, apply the same natural near-cap utilization to later ASINs in that sequence unless the user requests a shorter style, a different field format, or a verified category rule requires another limit. Re-verify every SKU's facts; only the format/density preference carries forward.
4. **Count deterministically before delivery.** Use a script/tool to report both character count and UTF-8 byte count. Normalize title case/punctuation and verify that no exact word token appears more than twice. Do not eyeball counts.
5. **Show utilization compactly.** Provide a summary such as `Title 74/75`, `Item Highlights 124/125`, and `Search Terms 246/250 bytes`, followed by clean upload-ready fields.
6. **Apply stricter live rules.** The post-July-27 limits are the general non-media baseline; media and stricter category validators require their own current check.
7. **Keep compliance stronger than density.** Never use extra capacity to add unverified food-contact, safety, child-use, chemical-free, durability, packaging, or absolute performance claims.
8. **Backend-term allocation:** finalize title and Item Highlights first, then normalize their tokens and spend backend bytes on missing high-value roots from verified competitor/SERP language, product objects, and secondary scenarios. Amazon can combine tokens across fields, so if title already contains `pen` and `desk`, add the missing root `holder` rather than repeating `pen holder for desk`. Avoid brands, ASINs, promotions, punctuation stuffing, unsupported competitor features, unnecessary title duplication, and weak filler added only to hit 250 bytes. Keep terms lowercase, space-separated, deduplicated, and verify UTF-8 bytes deterministically.

## Parent/Child Variation Handling

When a supplied ASIN resolves to a variation family or redirects to a default child:

1. Identify whether the requested ASIN is the parent and record the actual child ASIN whose public title/bullets were extracted.
2. Build a child configuration matrix from public variation data before drafting: child ASIN, pack count, size, color/material, and mixed-size status.
3. Produce a **parent-safe title** without child-only quantity/size/color attributes and a separate child-specific title for the selected SKU when useful.
4. Do not publish child-specific bullets or Item Highlights across the whole family. If bullets are shared, make them variation-safe or draft separate child copy.
5. Explicitly flag mixed-size children; never inherit a single-size phrase such as `4-5 Inch` into a mixed-size child.
6. In the final approval checklist, state exactly which ASIN each field applies to.

## Batch Item Highlights for Related ASINs

When the user asks for Item Highlights for multiple related ASINs or pack-size/refill variants:

1. Retrieve every child ASIN separately; do not assume sibling variants share the same included components.
2. Build a compact configuration matrix before drafting: handle count, holder/base count, refill count, dimensions, compatibility, and explicit exclusions.
3. Identify the purchase-decision difference for each ASIN and lead with it. Examples: multi-room value set, complete starter kit, or refill-only restock pack.
4. For refill-only ASINs, explicitly state `Refill Heads Only` and `Handle/Holder Not Included` when verified; preventing package-content confusion takes priority over adding another generic benefit.
5. Keep each US Item Highlights field at ≤125 characters, embed a core keyword in one coherent native phrase, and avoid both comma-joined Search Terms and shortened Bullet 1 copy.
6. Reuse verified family-level benefits only after confirming they apply to every ASIN. Never carry dimensions, counts, included parts, compatible surfaces, or system compatibility from one sibling to another without checking.
7. In Stage 1, show the verified configuration matrix and proposed emphasis order, then request approval. After approval, output upload-ready English Item Highlights plus Chinese translations and character counts.

## Product-Class References

- For US metal wall file organizers, hanging file holders, wall-mounted mail sorters, and tier/count variants, consult `references/us-wall-file-organizer-short-fields.md` for child-level base/hook/tier verification, brandless keyword-dense short titles, title-style Item Highlights, backend-term allocation, and claim guardrails.
- For US metal magazine-file holders, binder organizers, and vertical desktop file racks, consult `references/us-metal-magazine-file-holder-copy.md` for product-fact gates, market-language families, title/bullet differentiation, and compartment/color variation handling.
- For US multifunction mesh desk organizers combining paper trays, upright file sections, pen holders, drawers, or handles, consult `references/us-multifunction-desk-organizer-copy.md` for component-count separation, conflicting-dimension handling, short-title allocation, and review-informed assembly claim guardrails.
- For US metal bird baths, freestanding birdbaths, outdoor bird water stations, and bird-bath/feeder combinations, consult `references/us-outdoor-bird-bath-short-fields.md` for measurement disambiguation, keyword families, short Title/Item Highlights allocation, feeder/fountain truth checks, and rust/stability claim guardrails.
- For US decorative wired ribbon, velvet Christmas ribbon, wreath ribbon, and seasonal craft-ribbon ASINs, consult `references/us-decorative-wired-ribbon-short-fields.md` for child-spec verification, brandless keyword-dense title allocation, use-case compression, backend intent families, and finish/performance claim guardrails.
- For US tiered letter trays, paper organizers, desktop file organizers, and sibling SKUs that differ by drawers or pen holders, consult `references/us-tiered-letter-tray-organizers.md` for child mapping, SKU differentiation, short-field allocation, and claim guardrails.
- For US small PVC/mesh zipper pouches, bill-size storage bags, pencil pouches, board-game component bags, and 30/45/60-pack siblings, consult `references/us-small-mesh-zipper-pouches.md` for child mapping, title/highlight allocation, natural capitalization, and waterproof-claim guardrails.
- For US adjustable wedding welcome-sign stands, seating-chart holders, tall gold sign frames, and event poster stands, consult `references/us-adjustable-wedding-sign-stands.md` for component verification, two-height/spec allocation, Amazon autocomplete keyword families, outdoor/rust/load claim guardrails, and main-image package-content accuracy.
- For US wall file organizers, hanging wall files, vertical mail organizers, and dual-use desktop/wall-mounted file holders, consult `references/us-wall-file-organizer-short-fields.md` for child/parent fact verification, keyword families, base-versus-scenario allocation, Item Highlights structure, and backend Search Terms.

## Short-title field allocation reference

For the user-corrected workflow that balances core keywords, advantages, and use cases in Item Highlights—and then regenerates de-duplicated backend terms—consult `references/short-title-highlight-search-term-allocation.md`.

## Long Multi-Stage Analysis: Progress and Recovery

For staged research workflows that require many large SellerSprite/SIF/review calls, protect the user-visible progress trail:

1. **Acknowledge the approved transition.** When the user says `认可/继续`, state the exact next stage and scope before beginning the next research batch.
2. **Use bounded batches.** Do not accumulate a long chain of large tool results across multiple subphases without a user-facing synthesis. Complete one coherent batch—such as keyword competition, competitor details, or review mining—then publish a concise checkpoint or the stage report before starting another heavy batch.
3. **Never leave a stage ending on raw tool output.** After data calls finish, the same active turn should produce a visible message stating what was completed, which ASINs/keywords were covered, any gaps, and the next approval point. Tool completion without synthesis is not user-visible progress in chat channels such as Feishu.
4. **Recover instead of restarting.** If a session expires after the tools ran but before synthesis, use conversation history to recover the exact ASIN, marketplace, approved stage, product corrections, completed calls, and remaining synthesis. Do not ask the user to resend facts already verified.
5. **Report the interruption precisely.** Distinguish `data collection completed but synthesis was not delivered` from `no work was done`. Give a compact recovered-status checklist and resume from the missing deliverable.
6. **Do not overstate completion.** Call a phase complete only when both data collection and the user-facing report have been delivered.

## Common Pitfalls

0. **Stopping after a recoverable data timeout.** Large SellerSprite/SIF responses can be truncated or time out. Retry immediately with a narrower evidence-preserving query—such as an exact `keywordList`, fewer ASINs, smaller page size, or one primary metric—and continue into the requested deliverable in the same response. Do not make the timeout explanation a separate stopping turn after the retry has succeeded; briefly disclose the limitation alongside the actual result.
1. **Writing optimized copy before the audit is approved.** Stage 1 must end by asking for recognition/approval.
2. **Scoring SEO from copy appearance instead of keyword evidence.** A title can contain core roots and still rank poorly. Before assigning a strong SEO score, compare own traffic share and natural/ad positions against the same competitor terms. Do not treat a zero summary-stat response as proof of no keywords until the detailed keyword rows are checked.
3. **Using the old long-title format.** Post-July-27 non-media work must use Title ≤75 characters and Item Highlights ≤125 characters; media or stricter category validators require a separate current check.
3. **Stuffing every keyword into the title.** Title is now a mobile product-identification field; long-tail and COSMO intent live elsewhere.
4. **Ignoring Item Highlights.** It is searchable and visible; use it for material/use-case phrases.
5. **Missing brand/product consistency errors.** Wrong brand names in bullets are P0 issues.
6. **Missing brand/product/variation consistency errors.** Wrong brand names in bullets are P0 issues. A submitted ASIN may redirect to a default child while exposing a different canonical parent; the submitted ASIN is not automatically the parent and may not appear in the visible variation map. Record all three identifiers—submitted ASIN, resolved saleable child, and `parentAsin`—plus the selected attributes. Do not put the resolved child’s pack count, compartment count, size, or color into the parent title or shared family bullets. Build and display the variation matrix first, and confirm child-specific versus family-safe scope when the identifiers differ.
7. **Overclaiming protection or food use.** Hardware, safety, medical, child, pest, waterproof, rustproof, durability, baking/cooking, food-contact, coating/dye, and `safe/non-toxic` claims need qualification or evidence unless verified.
8. **Treating COSMO as keyword stuffing.** COSMO optimization means semantic purchase-intent coverage: tasks, scenarios, objections, and use cases.
9. **Forgetting data source labels.** Every metric must say whether it came from SellerSprite, SIF, Amazon page, or user-provided documents.
10. **Missing the latest-format trigger.** Do not fall back to the older long-title preference. Produce the post-July-27 ≤75-character non-media Title, verify it programmatically, and add Item Highlights ≤125 characters.
11. **Paraphrasing the title instead of adding value.** Token deduplication is not enough: `sliding trays` in the title and `pullout tiers` in Item Highlights are the same feature. Remove the semantic duplicate and use the space for the highest-priority uncovered keyword family first, then verified material, handle, storage objects, component counts, or scenarios. Do not inflate `with handle` into `a carry handle` unless portability is a separately verified, conversion-relevant distinction.
12. **Writing an attribute narrative before allocating keywords.** A fluent sentence about `reinforced steel frame` and `nonslip pads` can still be a poor Item Highlight when the field misses core phrases such as `desk organizer` or `letter tray`. Build the Title/Highlight keyword allocation first; descriptive construction details are optional, not the organizing principle.

## Verification Checklist

Before final response:

- [ ] If the user only said “文案优化”, asked for or used ASIN/marketplace.
- [ ] Checked whether the submitted ASIN is a parent, selected child, or redirects to a default child; if variations exist, built the configuration matrix and mapped every draft to the correct ASIN.
- [ ] Current listing content was retrieved or missing content was explicitly stated.
- [ ] Keyword/intent coverage was based on tools or user-provided keyword lists.
- [ ] Stage 1 did not prematurely output optimized copy before approval.
- [ ] Stage 2 Title is ≤75 characters for post-July-27 non-media work; media/current stricter rules were checked when applicable.
- [ ] Item Highlights are ≤125 characters, carry the highest-priority uncovered core keyword/synonym from the Title/Highlight allocation map, read as one coherent phrase, and are neither comma-joined Search Terms nor attribute-heavy feature narration.
- [ ] No wrong brand, unverified absolute claim, prohibited promotional phrase, or decorative symbol remains.
- [ ] Competitor facts were not copied into the own-ASIN draft without independent verification.
- [ ] Missing conversion-critical specifications are surfaced in a human confirmation checklist; conditional old-copy claims are clearly marked.
- [ ] Competitor performance advantages are decomposed into copy vs reviews/A+/video/variations/price/traffic breadth rather than attributed to wording alone.
- [ ] Title term priority follows own-ASIN relevance/traffic contribution, not broad search volume alone.
- [ ] When backend Search Terms are requested, candidate roots came from supplied keywords/direct competitors/relevant SERP evidence, then visible-field duplicates were removed.
- [ ] Backend Search Terms contain no competitor brand/ASIN, unverified feature claim, promotion, punctuation stuffing, or duplicate token; UTF-8 length was tool-verified at ≤250 bytes.
- [ ] Output includes Chinese explanations unless user requested another language.
- [ ] After every large research batch, a user-visible checkpoint or stage report was delivered; the conversation does not end on tool output alone.
- [ ] If resuming an interrupted staged audit, recovered the approved stage and verified facts from history instead of asking the user to repeat them.
- [ ] All write operations are framed as recommendations requiring human/operations approval.
