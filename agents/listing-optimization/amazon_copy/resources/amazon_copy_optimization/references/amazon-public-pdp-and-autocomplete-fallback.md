# Amazon Public PDP and Autocomplete Fallback

Use this when the browser is challenged or SellerSprite/SIF is unavailable, but the public Amazon page can still be retrieved. This is a fallback for current public evidence, not a replacement for Seller Central, SQP, ABA, or stable rank tracking.

## Raw PDP extraction

1. Request the canonical PDP (`https://www.amazon.com/dp/<ASIN>?th=1&psc=1`) with a normal desktop user agent and `Accept-Language: en-US,en;q=0.9`.
2. Parse only fields supported by the returned HTML:
   - `<title>` and `#productTitle`
   - `#bylineInfo`, price, rating, review count
   - `#feature-bullets`
   - `#productOverview_feature_div`
   - `parentAsin`, `mediaAsin`, variation/twister data
   - image-block `hiRes` URLs
   - `#aplus` text and BSR/category metadata
3. Strip tags and HTML entities, normalize whitespace, and label the result as an Amazon public-page snapshot.
4. Programmatically count title characters, UTF-8 bytes, exact-token repetitions, bullet lengths, and backend-term bytes.
5. Do not infer missing variation children, package components, compliance certifications, or rank from absent HTML.

## Amazon autocomplete as keyword-language evidence

Endpoint pattern:

`https://completion.amazon.com/api/2017/suggestions?limit=11&prefix=<QUERY>&alias=aps&mid=ATVPDKIKX0DER`

Probe a query ladder around the product identity, attribute, size, color, use case, and synonym. Record returned suggestion strings as **Amazon autocomplete language evidence only**.

Autocomplete proves that Amazon recognizes a query formulation; it does not prove monthly search volume, ABA rank, purchase share, current organic rank, or conversion potential. Do not label suggestions as high-volume without SellerSprite/SIF/ABA data.

## Raw public SERP retry and extraction

When a broad interactive search page is challenged or raw HTML returns zero result cards, do not stop at autocomplete immediately:

1. Retry with a narrower high-intent query that adds one verified product attribute or mechanism, such as color + product identity or size + use case.
2. Try a category-scoped query or a harmless normal search parameter. A practical retry shape is `https://www.amazon.com/s?k=<QUERY>&crid=1`; in some public sessions it returned genuine cards after the base URL did not. Treat this only as a retry shape—not a durable bypass—and use only a response containing real `data-component-type="s-search-result"` cards.
3. Parse each card's `data-asin`, H2 title, price, rating, review count, position, and Sponsored label. Deduplicate ASINs and keep organic/sponsored status separate.
4. Verify the own ASIN's position in the same response, then open 2–3 same-form competitors separately for bullets and factual comparison.
5. Label positions and prices as a one-time public SERP snapshot. A successful narrower query does not prove the broad-query rank, stable traffic, or monthly demand.
6. If review pages return no bodies, do not invent competitor pain points. Repeated competitor bullet themes may be reported only as inferred buyer questions or market objections.

This is a retry strategy, not a claim that one URL shape will always bypass challenges. If no genuine cards are returned after a small number of query variations, fall back to autocomplete and disclose the rank gap.

## PDP fallback verification traps

- The browser page title may prepend a brand even when the editable Product Title itself does not contain that brand; compare `<title>` with `#productTitle`.
- A technical A+ block may exist while its copy is generic or contradictory. Extract and audit the actual text; do not score A+ from presence alone.
- Main-image and package-content accuracy require reading the active image stack, not every preloaded `hiRes` URL from sibling variations.
- Public copy can contain stale or contradictory claims. Treat old bullets and image text as claims to verify, not product facts.
- If Amazon search result pages are blocked, do not fabricate competitor positions. Use autocomplete for language evidence and disclose that rank/competitor data is unavailable.