"""Profile + calendar YAML loading, and picking this week's workbook."""

import glob
import os

import yaml

from ... import _IS_SOURCE_CHECKOUT, _REPO_ROOT
from ...core.refs import _resolve_path
from ...errors import ProfileError
from ...model import HandlerSpec, Profile, ProfileInputs


def load_profile(path):
    """Load a profile YAML into a :class:`~ranse.model.Profile`.

    Structural validation only — required ``inputs.template``, a well-formed
    ``handlers:`` list. Whether a handler *name* exists and whether its
    ``params`` make sense is checked by the handler registry (decision 2 +
    "each handler validates its own params").
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ProfileError(f"{path}: profile must be a YAML mapping")

    raw_inputs = raw.get("inputs")
    if not isinstance(raw_inputs, dict):
        raise ProfileError(f"{path}: profile is missing the 'inputs:' mapping")
    template = raw_inputs.get("template")
    if not isinstance(template, str) or not template.strip():
        raise ProfileError(
            f"{path}: profile is missing 'inputs.template' (the workbook "
            f"to fill)")
    inputs = ProfileInputs(
        template=template.strip(),
        templates=_week_map(raw_inputs.get("templates"), path),
        extra=_extra_inputs(raw_inputs, path),
    )

    raw_handlers = raw.get("handlers")
    if raw_handlers is None:
        raw_handlers = []
    if not isinstance(raw_handlers, list):
        raise ProfileError(f"{path}: 'handlers' must be a list")
    handlers = []
    for i, entry in enumerate(raw_handlers, start=1):
        if not isinstance(entry, dict):
            raise ProfileError(f"{path}: handlers[{i}] must be a mapping")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ProfileError(f"{path}: handlers[{i}] is missing 'name'")
        params = entry.get("params") or {}
        if not isinstance(params, dict):
            raise ProfileError(
                f"{path}: handlers[{i}] 'params' must be a mapping")
        handlers.append(HandlerSpec(name=name.strip(), params=params))

    context = raw.get("context") or {}
    if not isinstance(context, dict):
        raise ProfileError(f"{path}: 'context' must be a mapping")

    name = raw.get("profile")
    if not isinstance(name, str) or not name.strip():
        name = os.path.splitext(os.path.basename(path))[0]

    return Profile(name=name.strip(), inputs=inputs, context=context,
                   handlers=handlers,
                   base_dir=os.path.dirname(os.path.abspath(path)))


def _extra_inputs(raw_inputs, path):
    """Every ``inputs:`` key except ``template``/``templates``, verbatim.

    The framework only shape-checks them: a value is a non-empty string
    (the common case — a path) or a mapping; ``None`` means "absent".
    Whether a key exists and what it means is the business of the
    handler/reader that declares it — the same contract as handler
    ``params``, which each handler validates itself.
    """
    extra = {}
    for key, value in raw_inputs.items():
        if key in ("template", "templates"):
            continue
        if not isinstance(key, str) or not key.strip():
            raise ProfileError(
                f"{path}: 'inputs' keys must be non-empty strings")
        if value is None:
            continue
        if isinstance(value, str):
            if not value.strip():
                raise ProfileError(
                    f"{path}: 'inputs.{key}' must be a non-empty string")
            extra[key] = value.strip()
        elif isinstance(value, dict):
            extra[key] = value
        else:
            raise ProfileError(
                f"{path}: 'inputs.{key}' must be a non-empty string "
                f"or a mapping")
    return extra


def _week_map(value, path):
    """``inputs.templates``: week number → workbook path (keys → str)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProfileError(f"{path}: 'inputs.templates' must be a mapping "
                           f"of week number → path")
    out = {}
    for key, raw_path in value.items():
        try:
            week = int(key)
        except (TypeError, ValueError):
            raise ProfileError(
                f"{path}: 'inputs.templates' key {key!r} is not a week number")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ProfileError(
                f"{path}: 'inputs.templates.{key}' must be a non-empty string")
        out[str(week)] = raw_path.strip()
    return out


def input_bases(profile=None, first=None):
    """Where relative input paths are looked up, in order.

    ``first`` (e.g. the folder of a data file whose paths resolve next to
    it), then the profile's own folder, then the current directory, then —
    **only in a source checkout** — the repository root. An installed
    package contributes no root: guessing beside site-packages would be
    worse than not falling back at all.

    This is the one place the base list is built; handlers and the profile
    loader share it so relative paths resolve the same everywhere.
    """
    bases = []
    if first:
        bases.append(first)
    if profile is not None:
        bases.append(profile.base_dir)
    bases.append(os.getcwd())
    if _IS_SOURCE_CHECKOUT:
        bases.append(_REPO_ROOT)
    return bases


def resolve_template(profile, template_vars=None):
    """Pick the workbook to fill (decision 10 + ``{week}`` patterns).

    ``template_vars`` is what the resolvers published into
    ``ctx.template_vars``; ``{week}`` inside ``inputs.template`` and the
    ``inputs.templates`` override key are read from its ``"week"`` value —
    the framework never derives a week number itself.

    Order: ``inputs.templates[week]`` → ``inputs.template`` with ``{week}``
    substituted. A pattern may contain glob wildcards; it must match exactly
    one existing workbook, otherwise the error lists the candidates and
    points at ``inputs.templates``.
    """
    week = (template_vars or {}).get("week")
    inputs = profile.inputs
    override = inputs.templates.get(str(week)) if week is not None else None
    raw = override or inputs.template

    if "{week}" in raw:
        if week is None:
            raise ProfileError(
                "the profile's template uses {week} but no week number is "
                "known — a resolve-phase handler must publish one, or pin "
                "the workbook with inputs.templates")
        raw = raw.replace("{week}", str(week))

    if not glob.has_magic(raw):
        path = _resolve_path(raw, input_bases(profile))
        if not os.path.isfile(path):
            raise ProfileError(f"file not found: {path}")
        return path

    matches = []
    for base in input_bases(profile):
        for hit in sorted(glob.glob(os.path.join(base, raw))):
            if hit not in matches:
                matches.append(hit)

    if not matches:
        raise ProfileError(
            f"no workbook matched {raw!r}"
            + (f" for week {week}" if week is not None else ""))
    if len(matches) > 1:
        raise ProfileError(
            f"{raw!r} matches {len(matches)} workbooks for week {week}: "
            + ", ".join(matches)
            + " — add an explicit 'inputs.templates' entry to the profile")
    return matches[0]
