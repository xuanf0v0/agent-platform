# Structured Fact Authorization and Cascade Dedupe

Cross-category operating rule for specialized-fact findings, packaging ambiguity, and rewrite order. Internal non-authoritative guidance: shapes diagnosis and copy instructions only; never authorizes a product fact by itself.

## 1. Merge root causes before rewriting

Multiple field findings often share one unauthorized fact key. Do not treat each bullet warning as an independent copy defect.

| Pattern | Correct response |
|---|---|
| Same `fact_key` on Title + several bullets | One **listing-level** missing-authorization root + field hits only where the claim text appears |
| Accessory count shared across two BOM lines | One **packaging ambiguity** root until counts are split |
| Unit conversion pair (`68 in` vs `5.7 ft`) | One **canonical unit/value** root, not two independent dimension errors |

Workflow: fix the **product fact source** first; then edit only fields that cite the unauthorized value.

## 2. Two-layer finding model

| Layer | When | How to report |
|---|---|---|
| **Listing-level gap** | SKU fact table lacks `verified` for a required key | Report **once** per `fact_key` (do not fan out to every bullet) |
| **Field-level misuse** | A specific field text contains an unauthorized number, count, or claim | Report only that field + the claim excerpt |

Validators and human reports must not imply “20+ independent errors” when five bullets all cite the same pending `height_settings`.

## 3. SKU structured authorization table

Before Stage 2 rewrite of precision claims, bind facts to one ASIN/SKU (never inherit sibling variation values without confirmation):

```yaml
product_identity:
  asin: null
  sku: null
  marketplace: null

authorized_facts:
  <fact_key>:
    value: null          # scalar, list, or structured object
    source: null         # document / photo / measurement id
    status: pending      # pending | partially_verified | verified
```

Typical keys (adapt per profile): `height_settings`, `overall_dimensions`, `base_dimensions`, `sign_thickness`, `included_water_bags`, `leather_straps` / `included_straps`, `weight_range`, `age_range`, `included_structure`, materials, exclusions.

### Status semantics

| Status | May write | Must not write |
|---|---|---|
| `pending` | Nothing that asserts the fact | Counts, sizes, “includes …”, performance numbers |
| `partially_verified` | Qualitative part only (e.g. bags included, height adjustable) | Unconfirmed count, exact heights, tested thickness |
| `verified` | Exact values from the table, single unit system | Sibling SKU values, competitor values, rounded dual-unit “equivalents” as if exact |

## 4. Evidence source priority

Highest to lowest. Lower ranks never override higher ranks.

1. Final BOM / packing list  
2. Packaging, manual, on-product labels  
3. Engineering drawings, spec sheets, QC / test reports  
4. Physical measurement with clear photos  
5. Written SKU-owner confirmation  
6. Live listing or supplier marketing copy — **clue only**  
7. Competitor listings — **never** our product truth  

“Old copy already said so” is not authorization.

## 5. Packaging and count ambiguity

Shared counts such as `with 8 Leather and Water Bags` are blocked until split:

```yaml
package_contents:
  leather_straps: { count, colors, quantity_per_color, source, status }
  water_bags: { included, count, fillable, source, status }
  other_line_items: ...
```

After verification, write itemized language (`Includes 8 leather straps and 2 fillable water bags`). Never infer counts from grammar alone. Do not paste another SKU’s strap/color matrix onto an unanchored ASIN.

## 6. Precision vs mechanism

| Unconfirmed | Allowed if mechanism is true | Delete |
|---|---|---|
| Exact sizes / height stops / counts | Qualitative structure (`adjustable height`, `rectangular base`, `leather straps hold boards`) | Specific inches/cm, “two heights”, pack counts |
| Max thickness / load | Non-numeric fit description | Test-style compatibility promises, `securely holds any` |
| Included accessory | — | `includes …` and quantities |
| Dual unit systems | One official unit across all fields | Mixing `68 in` and `5.7 ft` as identical precise facts |

Rule: **keep verified mechanisms; drop unconfirmed precision and performance promises.**

## 7. Field responsibility (dedupe copy)

| Field | Role |
|---|---|
| Title | Product identity + **one** strongest verified differentiator |
| Item Highlights | Pack contents or key verified specs (≤ budget) |
| Bullets | One buyer intent each (structure / specs / base·accessories / compatibility / contents·limits) |
| Backend terms | Incremental search roots only after visible fields are final |

Do not force the same dimension into every bullet. Listing-level required facts are not “must appear in bullet 1–5.”

## 8. Degradation matrix

| Missing authorization | Copy degradation |
|---|---|
| Accessory included? | No `includes …` |
| Accessory count | No number; never share a count across two types |
| Exact heights | `adjustable height` only if adjustability is verified; no `two heights` or inch pairs |
| Base size | `rectangular base` without numbers if shape is clear |
| Max board thickness | Drop `up to N cm/in` |
| Outdoor / wind / rust / heavy duty | Supervised / level-surface limits only; no performance absolutes |
| Fit ranges (weight/age) | Only packaging/manual-backed ranges |

## 9. End-to-end process

1. Anchor ASIN/SKU (and selected child when parent-submitted).  
2. Collect BOM, packaging, manual, drawings, tests.  
3. Fill structured authorization table with status.  
4. Resolve accessory count ambiguity item-by-item.  
5. Run global fact consistency (units, parent/child, title vs bullets).  
6. Edit **only** fields that cite unauthorized values.  
7. Re-check Title ≤75, Item Highlights ≤125, Backend ≤250 UTF-8 bytes.  
8. Deliver three blocks: verified facts / still pending / recommended copy.  
9. Human approval before any live listing change.

## 10. Diagnosis and UI messaging

- Prefer root-cause tables over raw finding dumps.  
- Cascade findings for one `fact_key` → one primary issue + optional field excerpts.  
- Clarification questions: one confirm/remove (or value) per root fact, not per bullet.  
- Stage 2 optimizer must consume `verified_facts` / structured claims; pending keys use the degradation matrix, never invent fillers.
