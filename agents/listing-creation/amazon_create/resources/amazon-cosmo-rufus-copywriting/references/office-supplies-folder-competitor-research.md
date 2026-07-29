# Office Supplies Folder Competitor Research Notes

Use when the user asks to find competitor ASINs for plastic pocket folders / school folders / project folders, especially by pack count and construction details.

## Recommended workflow

1. Start from the seed ASIN with `asin_detail` to identify exact product type, pack count, pocket count, prongs/holes, material, and price.
2. Use `traffic_listing` on the seed ASIN as the first competitor source. It returns more relevant related ASINs than broad title search for this category.
3. Use keyword/product search only as a secondary sweep. Broad queries such as `40 Pack Plastic Folders with Pockets` often return irrelevant high-volume products because `40`, `pack`, `pockets`, and `folders` match too broadly.
4. Filter strictly against the user's constraints:
   - Exclude titles containing `Prongs`, `Brads`, `Fasteners`, `Clasps` when the user says no prongs.
   - Treat `3 Hole Punched` as acceptable only if the user allows binder-hole folders; otherwise separate it from true no-hole/no-prong folders.
   - Exclude `binder pockets`, `clear sleeves`, `accordion folders`, and `paper folders` unless the user explicitly wants adjacent alternatives.
5. For pack-count requests, group by quantity first (e.g. 40pcs, 60pcs, 120pcs), then list ASIN, brand, title shorthand, and regular listing price.
6. To verify daily/non-promo price, call `asin_detail_with_coupon_trend` for shortlisted ASINs and use the ASIN detail `price` as regular listing price. If coupon/finalPrice is absent, state that no coupon adjustment was shown. Do not label it as historical average unless a price-history tool was used.

## Output format

Keep the answer concise and table-first:

| 数量 | ASIN | 品牌 | 标题简述 | 日常售价 |
|---|---|---|---|---|

Add short notes only for exclusions or uncertainty, e.g. `材质显示 Paper，严格塑料竞品可排除` or `3 Hole Punched，若严格不要打孔请排除`.

## Pitfalls

- Do not dump all related ASINs when the user asks for a narrow pack-count list.
- Do not include prong/fastener products after the user says `不要有Prongs`.
- Do not treat broad search results as reliable without title filtering; the query may match paper towels, sheets, clothing pockets, or unrelated pack-count products.
- Do not call coupon-adjusted price “日常价”; daily price should be the listing price before coupons unless the user asks for deal price.