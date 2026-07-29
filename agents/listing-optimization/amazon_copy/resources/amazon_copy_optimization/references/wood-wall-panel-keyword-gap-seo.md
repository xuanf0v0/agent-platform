# Wood/acoustic wall-panel keyword-gap SEO pattern

Use this reference when optimizing an already-live US wood slat/acoustic wall-panel listing against Art3d, TONOR, Avana, NeatiEase, or similar competitors.

## Non-negotiable workflow

Do not assign a high SEO score from copy structure alone. Before scoring or rewriting, pull own-ASIN and competitor keyword data and compare the same terms across ASINs.

1. Pull SellerSprite `traffic_keyword` for own child ASIN, relevant parent/bestselling sibling, direct competitor, and one strong keyword benchmark.
2. Use the same marketplace/month and order by traffic percentage. Capture keyword, traffic share, organic position, ad position, searches, purchases/purchase rate, product count, and supply-demand ratio.
3. Build a same-keyword matrix for at least:
   - `wall panels`
   - `wood panels for wall`
   - `acoustic wall panels`
   - `wall panels for interior wall decor`
   - `wood wall panels`
   - `wood slat wall panel`
   - `acoustic panels`
   - `wall paneling`
   - `slat wall paneling`
   - `3d wall panels`
   - `accent wall panels`
   - `decorative wall panels`
   - `acoustic wood wall panels`
   - `sound absorbing panels`
4. Separate direct-form competitors from adjacent keyword leaders. A 47.2 x 23.6 wide panel may be useful as an SEO/rank ceiling but not for direct area/spec value comparison with a 92–95 inch long strip.
5. Diagnose ad-to-organic gaps: strong ad position plus weak natural position means the term is receiving paid exposure but has not fully sedimented into natural rank. Listing relevance/CVR may be part of the constraint; do not treat it as a bid-only issue.
6. Allocate the highest-value verified phrases across title and bullets. Title gets the largest relevant entry terms; bullets receive precise morphology, decor-intent, material, acoustic, and installation phrases.
7. Recheck title repetitions, title length, total bullet length, exact phrase coverage, naturalness, product truth, and claim risk.

## SellerSprite summary/detail safeguard

`traffic_keyword_stat` can return `keywords=0`, `ranks=0`, and `ads=0` for a new child even when `traffic_keyword` returns a populated keyword list with current positions. Treat the summary as a quick indicator only. Before declaring a cold start or no keywords, call the detailed endpoint and verify whether `data.items` is populated.

When the normal SellerSprite tools are not exposed but the active profile already has `SELLERSPRITE_API_KEY`, use the established read-only Streamable HTTP MCP fallback without printing the key. List the target tool schema first, then call `traffic_keyword`; verify `isError=false`, requested ASIN, marketplace/month, populated rows, and row timestamps.

## Scoring rule

A data-backed SEO score must show its chain:

`own traffic share + organic/ad rank → competitor same-word rank → gap priority → title/bullet allocation → length/repetition/claim verification`

Do not raise a score merely because more keywords were inserted. A 9+ structural SEO score requires strong coverage of the listing's verified traffic concentration, natural phrasing, correct product intent, and explicit exclusion of misleading high-volume terms. It is not a promise of ranking improvement; SQP, CTR/CVR, and 2–4 week rank movement remain the outcome validation.

## Category-specific guardrails

- Do not front-load coverage area when a direct competitor offers materially more area at a similar regular price. Keep area in a dimensions/specification bullet or image for expectation management.
- Do not use `soundproof`, `noise cancelling`, foam, or peel-and-stick traffic merely because search volume is high when the product does not match that promise/form.
- Prefer qualified acoustic language: `helps soften everyday echo`, `sound absorbing support`, and a clear statement that the panels do not completely soundproof a room.
- Keep core purchase truth visible: long-panel dimensions, pack count, MDF slats, polyester felt backing, cut-to-fit/install method, and color.