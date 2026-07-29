# US Short Title + Item Highlights + Backend Search Terms

Use this reference when a user asks for a US short title (`≤75 characters`), Item Highlights (`≤125 characters`), competitor analysis, and backend Search Terms (`≤249 UTF-8 bytes`) for an existing child ASIN.

## Evidence order

1. Open the supplied child ASIN and extract title, bullets, brand, selected ASIN, parent ASIN, variation/color, category path, visible rating/review count, dimensions, material, compartment count, and included components.
2. Open the parent ASIN and verify whether it redirects to the selected child. Keep child-only color/count out of parent-safe copy.
3. Open the supplied competitor and compare product-form parity, structure, material, title roots, quantified features, rating/review evidence, and category node.
4. Run one precise Amazon query containing product form + key configuration/material. Label result positions as a location/time-sensitive public snapshot, not persistent rank or search volume.
5. Never borrow competitor-only facts such as non-slip feet, reinforced base, fully assembled construction, rust resistance, dimensions, or compatibility.

## Short-title allocation

Preferred structure:

`Brand + Core Product Phrase + Quantified/Structural Differentiator + Child Color`

- Keep one exact high-intent phrase, but do not repeat several reordered versions of the same tokens merely to preserve every long-tail phrase.
- Amazon can combine indexed tokens across fields; a title containing `desk`, `file`, and `organizer` need not repeat `file organizer for desk`, `desk file organizer`, and `desktop file organizer` verbatim.
- Replace vague adjectives such as `multi-functional` and `large capacity` with verified facts such as compartment count, drawer, material, or pack composition.
- A pack count must not imply that packaging accessories are product units. If a 33-piece kit contains 30 cedar pieces + 3 bags, do not call it `33 Pack Cedar Rings and Balls`.
- Count characters/bytes and normalized exact-token repetition deterministically before delivery.

## Item Highlights balance rule

Item Highlights must not be a mechanical scenario list, a keyword-free benefit sentence, comma-joined Search Terms, or a shortened Bullet 1. Write one coherent product phrase that complements the Title.

Preferred balance:

`Naturally embedded core keyword + material/feature + functional benefit or quantified proof + 2–3 representative use cases`

Good allocation patterns:

- `[Core product phrase] with [verified structure] for [buyer benefit] at/in [2–3 contexts]`
- `[Core synonym] with [verified components], [short coherent clause describing range/use objects]`

Rules:

- Include at least one important core keyword or high-value synonym naturally in the grammar; never append several synonyms as a comma list.
- Use commas only to separate coherent clauses or tightly related details. Reject drafts shaped like `desk organizer, pencil holder, pen holder, metal mesh...` even if all tokens are relevant.
- Limit scenarios to 2–3 representative contexts unless the field would otherwise omit a critical buyer intent.
- Prioritize real advantages before scenarios: aroma/moisture support, tilted-slot access, modular expansion, verified spacing, smooth finish, compact footprint, etc.
- Use qualified wording for performance claims: `helps freshen`, `helps absorb moisture`, `helps reduce mustiness`.
- Do not claim mold prevention, dehumidification, absolute odor elimination, safety, rust resistance, or durability without support.
- Use the available character budget naturally; a clean 112–124/125 field is better than awkward filler added solely to reach 125.
- Read the draft aloud: it should sound like one native product description fragment, not Search Terms with punctuation and not a full bullet explanation.

## Backend Search Terms allocation

Build Search Terms only after finalizing title and Item Highlights.

1. Normalize title/highlight tokens to lowercase and remove already-covered roots where repetition adds no indexing value.
2. Add missing high-value roots from:
   - competitor title and bullets;
   - precise SERP title language;
   - verified product objects (binder, notebook, marker, paper, mail);
   - relevant secondary scenarios (vanity, classroom, dorm, waiting area).
3. Use title tokens plus new backend roots compositionally. Example: if title already has `pen`, add `holder`; do not repeat `pen holder for desk` when `pen` and `desk` are already indexed.
4. No brands, ASINs, promotional words, punctuation stuffing, or unsupported feature claims.
5. Keep lowercase, space-separated, no duplicates, and `≤249 UTF-8 bytes`.
6. Do not fill the final bytes with weak terms. Prefer a smaller high-relevance set over exact-cap filler.
7. For color variations, omit color from family-safe Search Terms unless a color has independent verified search importance and the field is child-specific.

## Output order

1. Competitor diagnosis and own-vs-competitor advantages.
2. Child title + character/byte/repetition verification.
3. Parent-safe title when applicable.
4. Item Highlights + character/byte verification and balance explanation.
5. Search Terms + UTF-8 byte count + source/intent buckets.
6. Human approval notes and unsupported competitor claims excluded.
