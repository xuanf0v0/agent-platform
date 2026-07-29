# Parent/Child Variation Copy Handling

Use this reference when the submitted ASIN resolves to a variation family or redirects to a child ASIN.

## Detection

1. Open the submitted ASIN and compare the requested ASIN with the final PDP URL/media ASIN.
2. Inspect Amazon variation/twister data for `parentAsin`, child `data-asin` values, variation labels, and `pageLoadURL` mappings.
3. Build a compact matrix before drafting: parent ASIN, child ASIN, pack count, size, color/material, mixed-size status, and selected/default child.
4. State explicitly whether the extracted title/bullets belong to the parent, selected child, or a shared family contribution.

## Copy Rules

- Parent title: omit child-only quantity, size, color, or configuration. Keep only facts true for every child.
- Child title: include the selected child’s verified pack count/size/configuration.
- Shared bullets/A+/Item Highlights: never hard-code one child’s quantity or dimensions unless the content is child-specific. Use a family-safe formulation or provide separate child copy.
- Mixed-size children must not inherit a single-size title.
- Do not assume sibling components or specs from the default child; verify each variation separately.

## Output Pattern

1. Variation matrix.
2. Parent-safe title/Item Highlights.
3. Default-child or requested-child title/Item Highlights.
4. State whether bullets are family-safe or child-specific.
5. Human upload checklist mapping every draft to its exact ASIN.

## Public-page Fallback

If dedicated variation data tools are unavailable, Amazon PDP scripts/twister DOM can expose the parent ASIN, child ASINs, selected option, display labels, and prices. Treat this as a current public-page snapshot and verify against Seller Central before upload.
