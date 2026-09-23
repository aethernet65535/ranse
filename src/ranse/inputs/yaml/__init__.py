"""Profile + calendar YAML loading, and picking this week's workbook."""

import glob
import os
import sys

import yaml

from ... import _REPO_ROOT
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
            f"{path}: profile is missing 'inputs.template' (the e-RPH "
            f"template xlsx)")
    inputs = ProfileInputs(
        template=template.strip(),
        jadual=_text(raw_inputs.get("jadual"), path, "inputs.jadual"),
        timetable=_text(raw_inputs.get("timetable"), path, "inputs.timetable"),
        csv=_text(raw_inputs.get("csv"), path, "inputs.csv"),
        templates=_minggu_map(raw_inputs.get("templates"), path),
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


def _text(value, path, key):
    """Optional path-ish field: str → stripped, anything else → None."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{path}: '{key}' must be a non-empty string")
    return value.strip()


def _minggu_map(value, path):
    """``inputs.templates``: minggu number → workbook path (keys → str)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProfileError(f"{path}: 'inputs.templates' must be a mapping "
                           f"of minggu number → path")
    out = {}
    for key, raw_path in value.items():
        try:
            minggu = int(key)
        except (TypeError, ValueError):
            raise ProfileError(
                f"{path}: 'inputs.templates' key {key!r} is not a week number")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ProfileError(
                f"{path}: 'inputs.templates.{key}' must be a non-empty string")
        out[str(minggu)] = raw_path.strip()
    return out


def _input_bases(profile):
    """Where relative profile input paths are looked up (decision: see README)."""
    return [profile.base_dir, os.getcwd(), _REPO_ROOT]


def resolve_template(profile, minggu):
    """Pick the workbook to fill (decision 10 + ``{minggu}`` patterns).

    Order: ``inputs.templates[minggu]`` → ``inputs.template`` with
    ``{minggu}`` substituted. A pattern may contain glob wildcards; it must
    match exactly one existing workbook, otherwise the error lists the
    candidates and points at ``inputs.templates``.
    """
    inputs = profile.inputs
    override = inputs.templates.get(str(minggu)) if minggu is not None else None
    raw = override or inputs.template

    if "{minggu}" in raw:
        if minggu is None:
            raise ProfileError(
                "the profile's template needs a week number ({minggu}) but "
                "none is known — set inputs.jadual in the profile")
        raw = raw.replace("{minggu}", str(minggu))

    if not glob.has_magic(raw):
        path = _resolve_path(raw, _input_bases(profile))
        if not os.path.isfile(path):
            raise ProfileError(f"file not found: {path}")
        return path

    matches = []
    for base in _input_bases(profile):
        for hit in sorted(glob.glob(os.path.join(base, raw))):
            if hit not in matches:
                matches.append(hit)

    if not matches:
        raise ProfileError(
            f"no workbook matched {raw!r}"
            + (f" for minggu {minggu}" if minggu is not None else ""))
    if len(matches) > 1:
        raise ProfileError(
            f"{raw!r} matches {len(matches)} workbooks for minggu {minggu}: "
            + ", ".join(matches)
            + " — add an explicit 'inputs.templates' entry to the profile")
    return matches[0]


def load_jadual_config(path):
    """Load jadual-minggu.yaml: {jadual: {siri: path}, jadual_siri: {minggu: siri},
    minggu: [{start, minggu, cuti, siri}...]}"""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg.get("minggu"), list) or not cfg["minggu"]:
        print(f"Error: {path} has no 'minggu' records", file=sys.stderr)
        sys.exit(1)
    cfg["_config_dir"] = os.path.dirname(os.path.abspath(path))
    return cfg
