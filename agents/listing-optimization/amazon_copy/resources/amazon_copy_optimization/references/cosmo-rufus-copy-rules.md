# COSMO / Rufus / Keyword Library Copy Rules

Source documents learned on 2026-07-02:
- COSMO翻译版.pdf
- COSMO与Rufus算法分析与运营策略docx.pdf
- AI文案撰写应用.pdf / .docx
- 亚马逊文案撰写要求.docx
- 广告知识库.docx

## 1. Core mental model

Amazon copy is no longer only keyword stuffing for A9. Treat the listing as a structured answer to buyer intent:

- **A9 / classic SEO**: cover high-relevance keywords and roots in title, bullets, description, Search Term, Q&A, reviews, and image/A+ context.
- **COSMO**: Amazon uses e-commerce commonsense knowledge graphs and LLM-derived intent knowledge to understand why users search/buy, not only what exact term they typed. Copy should expose product–intent relationships: use case, scenario, audience, material, problem, benefit, objection, and complementary context.
- **Rufus**: a front-end AI shopping assistant uses product details, reviews, Q&A, and comparison context to answer shopper questions. Copy/Q&A should make the product easy for Rufus to explain and compare.

Practical rule: for every important keyword, identify the buyer intent behind it and make sure the listing says why this product fits that intent.

## 2. COSMO/Rufus optimization rules for listing copy

When auditing or writing copy, check these content surfaces:

1. Title
2. Bullets / five points
3. Product description
4. A+ modules
5. Image text / image filenames / video names when relevant
6. Detail fields
7. Q&A
8. Reviews / review mining insights
9. Posts / store activity signals when relevant

Do not force all intents into the title. Use title for clear product identification, then distribute semantic intent coverage across bullets, Item Highlights, A+, images, Q&A, and Search Term.

## 3. Intent mining sources

Use multiple sources to discover buyer-intent language:

- Amazon search term reports / SQP / search query data: prioritize terms with strong conversion or purchase share.
- Competitor keyword reverse lookup: select TOP similar competitors, not just head sellers; similarity should include price, function, appearance, and product type.
- Search box autocomplete and bottom “Related searches”.
- Product reviews and Q&A: mine usage scenarios, pain points, objections, reasons for purchase, and satisfaction/dissatisfaction language.
- Reddit, Quora, forums, social media: extract native user phrasing and problem language.
- SellerSprite/SIF keyword data: traffic share, ABA rank/search volume, purchase rate, CPC, conversion, CPA/ACOS proxy, supply-demand, monopoly/concentration.

## 4. Keyword tagging model

Classify keywords before allocating them into copy:

- **Primary class**: product-name term, function term, scenario term, audience term, attribute term.
- **Secondary class**:
  - product-name term: no second-level class unless needed
  - function term: specific function/parameter
  - scenario term: specific use scene
  - audience term: specific buyer/user/animal group
  - attribute term: material, color, size, shape, quantity, variation, misspelling, language variant, etc.
- **Relevance**:
  - strong: search results are about 80%+ similar to our product
  - medium: about 50% similar
  - weak: about 20% similar
  - irrelevant: little/no similarity
- **Traffic size by ABA rank** as a starting point only:
  - big term: ABA < 30k
  - mid-tail: 30k–100k
  - long-tail: >100k
  - adjust thresholds by category because traffic scale is relative.
- **Orderliness**:
  - ordered phrase: can be covered by phrase match under a larger root/phrase
  - unordered/dispersed phrase: needs broad/auto exploration in ads; for copy, avoid overstuffing and cover intent semantically.

For copy work, use the tag output to build a keyword-to-intent-to-copy allocation table.

## 5. Copy quality checks from internal SOP

### Title

- Must comply with category length rules; internal SOP says keep titles concise and preferably under 80 characters when possible.
- Must not contain promotional phrases such as “free shipping” or “100% quality guaranteed”.
- Must not contain decorative/prohibited characters: `~ ! * $ ? _ { } # < > | ; ^ ¬ ¦` and avoid unnecessary symbols.
- Must include identifying product information, not merely broad terms.
- Do not use all caps.
- Capitalize major words; do not capitalize short prepositions/conjunctions/articles unless required by style.
- Use numerals, not spelled-out numbers.
- Do not use subjective claims like “Hot Item” or “Best Seller”.
- Do not put seller name in title.
- Parent ASIN title should not carry child-only color/size attributes; child ASIN title should contain the selected variation attributes.
- Long titles reduce scanability because shoppers skim search results.

### Bullets / five points

- Maximum five bullets.
- Internal SOP recommends the total length of all five bullets stays under 1,000 characters when possible for readability and potential discoverability.
- Avoid keyword stuffing; natural keyword inclusion is good, but the primary goal is decision support.
- Start from a feature, then translate it into a buyer benefit.
- Use one core intent per bullet when possible: e.g. comfort/support, portability, material/quality, installation/use, care/maintenance, compatibility, scenarios, trust.

## 6. Intent-driven copy structure

For each product, build an intent map before writing:

| Intent | Buyer question | Product proof | Copy surface |
|---|---|---|---|
| Comfort / efficiency / safety / convenience etc. | What problem is the buyer trying to solve? | Material, spec, design, test, review insight | Title / bullet / A+ / Q&A |

Examples from the travel pillow document:

- Comfort: memory foam adapts to neck/head shape.
- Neck support: ergonomic support reduces stiffness risk.
- Portability: compact/lightweight, fits carry-on.
- Versatility: airplanes, trains, cars, office naps.
- Hygiene: removable machine-washable cover.
- Sleep quality: supports head/neck in cramped airplane seats.
- Durability: materials withstand frequent travel.
- Additional features: pouch, phone/earplug pocket, etc. only if true.

Do not invent features. Convert only verified specs into benefits.

## 7. Q&A strategy for Rufus and buyer objections

For optimized listings, propose Q&A topics when relevant. Q&A should answer high-intent buyer questions directly, using natural marketplace language.

Q&A should cover:

- Fit/use-case suitability: “Is this suitable for …?”
- Portability/storage: “Will it fit in …?”
- Material/function mechanism: “How does … work?”
- Cleaning/care: “Is it washable/removable/easy to maintain?”
- User-type fit: side sleepers, renters, tall people, pets, kids, etc. where relevant.
- Multi-scenario use: home/office/car/travel/etc.
- Pain point relief: neck pain, noise, installation hassle, odor, overheating, etc. but avoid medical or absolute claims unless verified.
- Product comparisons: how it differs from common alternatives.

## 8. Funnel linkage from ad/keyword docs

Use keyword/listing diagnosis with funnel logic:

- Low/no impressions: may reflect missing/weak SEO term coverage, poor keyword precision, low listing weight, Buy Box/product status, or ad budget/bid/targeting issues.
- Low clicks / low CTR: search result page problem: title, main image, rating/review count, FBA/Prime, price, promotion, competitor context.
- Low CVR: detail page problem: title relevance, review trust, FBA, image set, A+, video, price, bullets, details, promotion, product quality, competitor comparison.
- High ACOS/TACOS can be caused by high bid, low CVR, low price, high ad-sales dependency, poor listing conversion, or weak natural keyword coverage.

As listing-optimization agent, diagnose listing-side issues and hand ad-side bid/budget/negative/placement actions to ad-optimizer; price/Coupon/Buy Box/inventory actions to operations/finance.

## 9. Required output additions for future copy audits

When doing “文案优化” or copy audit, include:

1. Keyword coverage table: keyword, tag, relevance, traffic tier, buyer intent, covered/missing, recommended surface.
2. COSMO/Rufus semantic coverage table: intent, buyer question, current proof, missing proof/content, suggested copy/A+/Q&A angle.
3. Competitor comparison should use at least 2–3 comparable competitor ASINs when available.
4. Copy quality scoring should include SEO keyword/root coverage and user-intent/COSMO coverage separately.
5. Do not output final rewritten copy until the user approves the audit unless the user explicitly asks to skip approval.
