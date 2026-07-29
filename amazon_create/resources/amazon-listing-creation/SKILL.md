---
name: amazon-listing-creation
description: Create Amazon listing Title and Bullet Points from scratch using a staged, user-gated workflow with market audience research, product-spec interpretation, optional competitor analysis, selling-point extraction, keyword layout, and localized copy.
---

# Amazon Listing Creation

## When to use

Use this skill when the user asks to create a new Amazon listing, especially Title and Bullet Points, from scratch rather than optimize an existing live ASIN.

Typical triggers:

- User provides a product name and target marketplace and asks for Title/Bullets.
- User wants a staged workflow before copywriting.
- User asks for audience research, purchase motivations, concern analysis, review pain points, competitor ASIN comparison, selling-point extraction, or keyword-first listing copy.

If the user is diagnosing or rewriting an existing live listing, use `amazon-listing-optimization` instead.

## Mandatory shared policy gate

Load `amazon-listing-policy-and-semantic-copy` before using this workflow. Its post-July-27-2026 policy, evidence hierarchy, review/variation rules, and deterministic checks override conflicting internal SOP instructions in this file.

## 2026 Amazon Title + Item Highlights Rule Update

Source learned from Amazon Seller Forums thread `145b6d0f-999c-4555-896c-c694bda2e470` (“Updates to improve your product titles begin on July 27”, updated Jun 10, 2026):

- Starting **July 27, 2026**, titles in **all categories except media** must be **75 characters or less including spaces**.
- Amazon provides **Item Highlights**: **125 searchable characters** for materials, recommended use cases, and comparison details, visible with titles in search results and on product detail pages.
- New SOP: write a compact mobile-first Title and move secondary selling points/keywords into Item Highlights, bullets, description, A+, and backend terms.
- After July 27, titles over 75 characters may be gradually updated to Amazon AI recommendations; brand owners get a **14-day review window** in Review Listings Changes.
- Default all new listing-creation work to the 75-character title standard. Do not output a legacy long-title branch. Retrieve the current category rule for media.

## Required staged workflow for Title + Bullet creation

Proceed in gates. Do not skip ahead unless the user explicitly asks to bypass a stage.

1. **Collect product name and target market**
   - Ask for product name and marketplace/language if missing.
   - Do not begin final copywriting before the marketplace is known.

2. **Market audience and demand research**
   - Use the number of audience, motivation, concern, and review themes supported by actual data; `Top 20` is an optional exploration ceiling, not a mandatory count.
   - Attach percentages only to a cited dataset and denominator. If live data is blocked or incomplete, output qualitative hypotheses without percentages and label them `hypothesis`.
   - After the analysis, ask whether the user approves before moving on.

3. **Product-spec interpretation**
   - Ask the user for product manual/specifications.
   - First explain the product class from multiple dimensions: key specs, materials, use cases, quality signals, safety/installation factors, and comparison dimensions.
   - Then interpret the user’s product specs and map each parameter/function to buyer needs.
   - Ask whether the user approves before moving on.

4. **Competitor analysis**
   - Ask the user for competitor ASIN(s) and marketplace in the format they prefer.
   - If they do not provide competitors, move to selling-point extraction.
   - If provided, research competitor Title and Bullet Points and compare against the user’s specs:
     - Functional/spec comparison.
     - Selling-point order in competitor bullets.
     - Copywriting style and level.
     - Gaps and opportunities.
   - Output comparison tables and ask whether the user approves before moving on.

5. **Selling-point extraction**
   - Based on audience needs, purchase motivations, competitor positioning, and the user’s product differences, extract and rank five selling points by importance.
   - The goal is to persuade the target audience, not merely list features.
   - Ask whether the user approves before moving on.

6. **Keyword research and final copywriting**
   - Build an evidence-ranked keyword library before writing:
     - Relevant roots, phrases, synonyms, and buyer questions supported by user data, first-party data, SellerSprite/SIF, or labeled public observations.
     - Title-critical terms vs Item Highlights terms vs Bullet/Backend support terms.
   - Use marketplace-native language and search behavior. Do not translate English keywords literally into another language.
   - Write Title, Item Highlights, and five Bullet Points only after the previous gates are approved.
   - When delivering the final draft, include the agreed add-ons when useful for launch readiness: Product Description, Backend Search Terms, A+ / EBC structure, compliance self-check, and clear `待补` items for missing specs.
   - After the user approves the listing copy, explicitly ask whether they need image design planning; if yes, proceed to a main image + 7 secondary image plan rather than asking them to restart the workflow.

## Title requirements for this workflow

- Use the target marketplace’s local language.
- Default non-media category title limit: **≤75 characters including spaces** (Amazon 2026 title update).
- Structure the title as a compact mobile-first line:
  1. Brand.
  2. Main core keyword.
  3. One critical functional feature, spec, pack/size, or differentiator.
- When size/spec determines fit or prevents returns, place the verified size/spec near the front even if that reduces keyword breadth.
- Embed only the top 1–2 title-critical keywords naturally; do not force 3–5 keywords if it breaks the 75-character limit.
- Move secondary buyer-demand features, materials, use locations, scenarios, target user/device/object, and extra roots/stems to **Item Highlights**, bullets, description, A+, and backend terms.
- Bold embedded keywords and roots/stems when presenting the draft for review, but provide an upload-ready version without Markdown when requested.
- Output both local-language copy and Chinese translation.
- Do not provide a legacy long-title variant unless the task is explicitly historical.

## Item Highlights requirements

- Output one Item Highlights line by default, **≤125 characters including spaces**.
- Treat Item Highlights as searchable front-end copy, not backend keyword stuffing.
- Use it to carry material, recommended use cases, comparison details, compatibility, quantity/color/set information, and high-value semantic terms that no longer fit in the 75-character title.
- Keep it readable as a short customer-facing search-result/detail-page support line.
- Do not include competitor brands, promotional claims, unverified absolutes, or unsupported performance claims.

## Bullet Point requirements for this workflow

- Write five bullets in the target marketplace’s language.
- Use only the length needed for clear, verified decision information; do not target a fixed bullet character range.
- Do not end English bullets with a period when the user requests that convention.
- Lead with buyer intent and benefit, then support with product parameter or use case.
- Make scenarios concrete and local to the target market.
- Embed only relevant, evidence-backed terms that preserve native readability. There is no minimum keyword or root quota.
- Bold embedded keywords and roots/stems in the review draft.
- Output local-language content first, then Chinese translation, without extra explanation when the user requests a strict copy block.

## COSMO / Alexa for Shopping (formerly Rufus) intent-first copy guidance

Use this when the user asks for COSMO, Rufus, or Alexa for Shopping-friendly listing copy or provides related SOP materials.

- Treat Amazon copy as an intent graph, not only a keyword container: map `buyer intent → use scenario → product attribute → proof/detail → benefit` before drafting.
- COSMO-friendly copy should cover broad concepts plus fine-grained long-tail intents: core category terms, related scenario terms, problem/solution language, material/spec terms, audience/device/occasion terms, and complementary-use terms.
- Alexa for Shopping-friendly copy should answer natural-language shopping questions inside Title/Bullets/Description/A+/Q&A: who it is for, when to use it, what problem it solves, what makes it different, how it compares, how to clean/install/use, and what is included.
- Build an “intent keyword” layer in addition to roots and keywords. Sources: Amazon search bar suggestions, related searches, SellerSprite keyword data, competitor Q&A/reviews, and product-specific buyer concerns.
- Draft bullets by intent cluster, not by random features. Recommended five-bullet order: primary outcome, differentiated feature/spec proof, scenario coverage, ease of use/care/compatibility, trust/risk reducer.
- Use semantic/contextual phrases naturally (e.g. `neck support for long flights`, `fits in a carry-on`, `machine-washable cover`) rather than repeating only exact-match short keywords.
- Plan evidence-based buyer-question topics when useful. Never fabricate or spam Q&A; never request positive-only reviews, incentivize reviews, gate negative feedback, ask for removal/change, or create variations to aggregate reviews.

## Compliance and claim discipline

- Never invent dimensions, gauge, material, count, certification, voltage, compatibility, warranty, or performance claims. Mark missing facts as `待补`.
- Avoid absolute claims such as `best`, `100%`, `guaranteed`, `indestructible`, `predator proof`, or `rustproof` unless the user provides strong substantiation and the claim is allowed.
- Prefer safer wording such as `helps protect`, `designed for`, `built for`, `helps resist rust`, and `suitable for`.
- For safety-sensitive categories or sharp metal products, include installation/safety reminders when appropriate, such as gloves and eye protection, but do not overstate safety guarantees.

## Hardware cloth class notes

For US hardware cloth listings, buyers commonly compare:

- Mesh opening size, especially `1/2 inch` or `1/4 inch`.
- Wire gauge and perceived toughness.
- Roll size: width and length.
- Material and finish: galvanized steel, welded wire mesh, rust resistance.
- Use cases: chicken coop, poultry run, garden fence, raised bed, gopher barrier, rabbit hutch, crawl-space vent, tree guard, pest barrier, DIY projects.

Positioning should usually prioritize chicken coop protection, garden/pest barrier use, heavy-duty gauge, galvanized welded construction, clear dimensions, and cut-to-fit DIY usability.

## Category / Browse Node Lookup for Launch Drafts

When the user asks which SellerSprite/Amazon category path a product should use:

1. Query SellerSprite `product_node` with the target marketplace and category keyword to get candidate `nodeIdPath` values.
2. Validate the terminal Amazon node by opening `https://www.amazon.<site>/b?node=<leafNodeId>` or checking the page title/breadcrumb; SellerSprite may return only IDs with null node names.
3. Cross-check at least one close competitor ASIN with `asin_detail` for its `nodeIdPath`; competitor paths reveal where similar products are actually selling.
4. Return both the human-readable path and full `nodeIdPath`, plus any shortened path SellerSprite/Seller Central may display without the top-level node.
5. If category positioning and copy intent differ, state the trade-off clearly. Example for UK kraft paper rolls: `Kraft Paper` fits craft/classroom/DIY positioning, while competitor gift-wrap products may sit under `Gift Wrapping Paper`; align title/bullets with the chosen category.

## Pitfalls

- Do not jump directly to copywriting after receiving only product name and marketplace if the user requested a staged workflow.
- Do not create directional percentages without a dataset; use qualitative hypotheses and label the basis clearly.
- Do not copy competitor phrasing. Extract structure and angle only.
- Do not let a product-class skill override the user’s required gatekeeping sequence.
- Do not ask for all future inputs at once if the workflow requires approval between stages.
- Do not keep writing 100–200 character titles as the default for non-media categories; use 75 characters and shift overflow into Item Highlights.
- Do not treat Item Highlights as a keyword dump; it is searchable and customer-visible, so it must read naturally.
