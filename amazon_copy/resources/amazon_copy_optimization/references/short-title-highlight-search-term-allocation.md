# Short Title, Item Highlights, and Search Terms Allocation

Use this reference for US short-title work when the requested team format is Title ≤75 characters, Item Highlights ≤125 characters, and backend Search Terms ≤249 UTF-8 bytes.

## Field roles

- **Title:** brand + primary product identity + decisive verified specification/variant.
- **Item Highlights:** one concise, coherent product phrase containing a naturally embedded core keyword or high-value synonym, a verified structure/advantage, its buyer benefit, and 2–3 representative use cases when space permits.
- **Search Terms:** relevant missing roots only—synonyms, item types, buyer tasks, secondary use cases, and stored-object nouns not already covered by Title/Highlights.

## Item Highlights quality gate

Reject and rewrite a draft if any condition is true:

1. It reads like a complete Bullet 1 explanation.
2. It contains no core product keyword or high-value synonym.
3. It reads like Search Terms with commas, for example `desk organizer, pencil holder, pen holder, metal mesh...`.
4. Most of the field is a mechanical list of rooms or scenarios.
5. It repeats the title’s full identity, count, and specifications without adding new intent.
6. It has benefits but no context, or scenarios but no verified product advantage.

Preferred shape:

`[core keyword embedded in product phrase] + with/featuring + [verified structure] + for [buyer benefit or stored objects] + [2–3 use cases]`

Commas are optional. Use them only where natural English needs a pause or separates two coherent clauses; punctuation must never be used to disguise a keyword list.

## Natural structural examples

These are patterns only. Re-verify every fact and count for the active ASIN.

- `Metal mesh pencil holder and desk organizer with tilted slots for easy access to stationery at home, school or office`
- `Wall organizer with mesh pockets, label panels and hook or screw mounting for A4 and letter files at home, office or school`
- `Metal mesh drawer organizer tray with 5 removable dividers, expands from 8.74 to 16 in for office supplies, makeup or tools`
- Craft-material Highlights pattern (when Title already holds brand/pack/size): `Smooth, flat seashells for painting, decoupage, coastal decor, beach weddings, and ocean-themed parties.` — surface + complementary intents only; no brand/pack/size echo.

Why these work:

- A core phrase is part of normal grammar rather than listed as a token.
- Material and structure lead directly to a use benefit.
- Scenarios or stored objects are secondary and limited.
- The phrase is informative without becoming a full bullet paragraph.
- Craft exemplar Highlights deliberately leave identity facts to the Title and spend budget on techniques/events.

## Cross-field keyword allocation

- Put one primary exact phrase in the Title.
- Use Item Highlights for one important missing synonym or alternate product phrase, embedded naturally.
- Do not force every phrase-order variant into either visible field. If `desk`, `file`, and `organizer` are already indexed, mechanically repeating `desk file organizer`, `file organizer for desk`, and `desktop file organizer` wastes characters.
- Amazon can combine indexed tokens across fields, but exact adjacency may still be used selectively for a verified priority query.
- A keyword requirement does not justify sacrificing readability. One natural phrase plus combinable roots is better than three comma-separated synonyms.

## Search Terms regeneration

Every Title or Item Highlights revision invalidates the previous backend allocation. Rebuild Search Terms after visible fields are final:

1. Normalize Title and Highlights to lowercase word tokens.
2. Remove brands, ASINs, promotions, punctuation, and duplicate words.
3. Remove words or obvious stems already covered in visible fields unless a distinct spelling/intent is needed.
4. Add relevant missing synonyms, stored objects, buyer tasks, and secondary scenarios from verified product facts, direct-competitor copy, and relevant SERP wording.
5. Do not import competitor-only features such as non-slip feet, dimensions, rust resistance, load limits, or assembly claims without own-product verification.
6. Keep terms lowercase and space-separated; verify ≤249 UTF-8 bytes programmatically.
7. Prefer 220–245 strong bytes over filling the cap with weak or speculative terms.

## Variation safety

- Keep child color/size/count in the child Title only.
- Produce a parent-safe Title when a parent or variation family is involved.
- Keep Highlights and Search Terms variation-safe when fields are shared across siblings.
- If a child-specific fact moves into Highlights, update sibling fields separately rather than copying it across the family.

## Final verification

- Title characters/bytes and exact-token repetitions counted deterministically.
- Item Highlights ≤125 characters and read aloud as natural US English.
- Item Highlights contain a core keyword naturally—not a keyword-free benefit sentence and not comma-joined Search Terms.
- Search Terms regenerated after the final visible copy and byte-checked at ≤249.
- All numbers labeled as user-provided, Amazon public-page evidence, SellerSprite/SIF evidence, or unverified.
