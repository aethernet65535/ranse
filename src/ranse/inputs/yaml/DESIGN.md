# YAML reader — schemas

This reader loads the two YAML documents a run needs: the **profile** and the
data file a handler references (here, the school calendar). It is a pure
input: it never touches the target workbook (decision 8,
[`docs/DESIGN.md`](../../../../docs/DESIGN.md)).

Both schemas are contract, so they are documented where they are defined
rather than here:

| Document | Loader | Schema |
|---|---|---|
| the profile | `load_profile` | [`docs/DESIGN.md`](../../../../docs/DESIGN.md) S3.3 (and the profile's own `DESIGN.md`) |
| the school calendar | `load_jadual_config` | [`config/jadual-minggu/DESIGN.md`](../../../../config/jadual-minggu/DESIGN.md) |

`resolve_template` (framework, decision 10) picks the workbook: the
`inputs.templates` override first, then `inputs.template` with `{week}`
substituted and glob wildcards expanded.
