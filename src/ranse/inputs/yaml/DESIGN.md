# YAML reader — schemas

This reader loads the profile, the one YAML document every run needs. It is
a pure input: it never touches the target workbook (decision 8,
[`docs/DESIGN.md`](../../../../docs/DESIGN.md)).

The schema is contract, so it is documented where it is defined rather than
here: the profile schema in [`docs/DESIGN.md`](../../../../docs/DESIGN.md)
S3.3 (and the profile's own `DESIGN.md`).

`load_profile` validates **shape only**: `inputs.template` (required),
`inputs.templates` (week-number → path) and, for every other key, "a
non-empty string or a mapping" — those keys are handler-specific and pass
through verbatim into `ProfileInputs.extra`; each handler/reader
validates the keys it declares, exactly like handler `params`.

Other YAML formats live in their own folder (one reader per format): the
school calendar is read by [`inputs/calendar/`](../../calendar/).

`resolve_template` (framework, decision 10) picks the workbook: the
`inputs.templates` override first, then `inputs.template` with `{week}`
substituted and glob wildcards expanded.
