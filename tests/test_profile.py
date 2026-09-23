"""Profile schema: explicit handlers, unknown names, param validation.

Stage 3 acceptance (docs/DESIGN.md §4): the three failure modes the registry owns —
unknown handler name, missing ``inputs.template`` and invalid handler params
— plus a check that the shipped profile only names registered handlers.
No ``assets/`` needed, so these run on a fresh clone.
"""

import textwrap
from pathlib import Path

import pytest

from harness import PROFILE_YAML, fn

build_handlers = fn("build_handlers")
HandlerSpec = fn("HandlerSpec")
ProfileError = fn("ProfileError")
load_profile = fn("load_profile")
resolve_template = fn("resolve_template")


def write_profile(tmp_path, body):
    path = tmp_path / "profile.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


# --- the shipped profile ---------------------------------------------------

def test_shipped_profile_names_only_registered_handlers():
    profile = load_profile(str(PROFILE_YAML))
    assert [spec.name for spec in profile.handlers] == [
        "week", "menu", "fixed_cells", "dskp"]
    build_handlers(profile.handlers)  # raises ProfileError on a bad name


def test_shipped_profile_resolves_its_inputs_against_itself():
    profile = load_profile(str(PROFILE_YAML))
    assert profile.inputs.template.endswith(".xlsx")
    assert profile.inputs.jadual.endswith("jadual-minggu.yaml")
    assert Path(profile.base_dir).name == "profiles"


# --- structural errors -----------------------------------------------------

def test_unknown_handler_name_is_an_error():
    with pytest.raises(ProfileError) as exc:
        build_handlers([HandlerSpec(name="not_a_handler", params={})])
    assert "unknown handler" in str(exc.value)
    assert "week" in str(exc.value)  # lists what is available


def test_missing_template_is_an_error(tmp_path):
    path = write_profile(tmp_path, """
        profile: p
        inputs:
          jadual: config/jadual-minggu.yaml
        handlers: []
        """)
    with pytest.raises(ProfileError) as exc:
        load_profile(str(path))
    assert "inputs.template" in str(exc.value)


def test_missing_inputs_section_is_an_error(tmp_path):
    path = write_profile(tmp_path, """
        profile: p
        handlers: []
        """)
    with pytest.raises(ProfileError) as exc:
        load_profile(str(path))
    assert "'inputs:'" in str(exc.value)


def test_handlers_must_be_a_list(tmp_path):
    path = write_profile(tmp_path, """
        profile: p
        inputs: {template: template.xlsx}
        handlers: week
        """)
    with pytest.raises(ProfileError) as exc:
        load_profile(str(path))
    assert "'handlers' must be a list" in str(exc.value)


def test_handler_entry_without_name_is_an_error(tmp_path):
    path = write_profile(tmp_path, """
        profile: p
        inputs: {template: template.xlsx}
        handlers:
          - params: {cells: []}
        """)
    with pytest.raises(ProfileError) as exc:
        load_profile(str(path))
    assert "handlers[1] is missing 'name'" in str(exc.value)


def test_handlers_default_to_an_empty_list(tmp_path):
    path = write_profile(tmp_path, """
        profile: p
        inputs: {template: template.xlsx}
        """)
    profile = load_profile(str(path))
    assert profile.handlers == []
    assert profile.name == "p"


# --- params validation (each handler validates its own params) -------------

def test_fixed_cells_params_shape_is_validated():
    with pytest.raises(ProfileError) as exc:
        build_handlers([HandlerSpec(
            name="fixed_cells", params={"cells": [["MENU", "B3:C3"]]})])
    assert "cells[1]" in str(exc.value)


def test_fixed_cells_accepts_the_shipped_shape():
    build_handlers([HandlerSpec(
        name="fixed_cells",
        params={"cells": [["MENU", "B3:C3", "ALI BIN ABU"], ["MENU", "B4", 1]]})])


def test_dskp_unknown_mode_is_an_error():
    with pytest.raises(ProfileError) as exc:
        build_handlers([HandlerSpec(name="dskp", params={"mode": "sometimes"})])
    assert "unknown mode" in str(exc.value)


def test_dskp_static_entry_requires_sheet_and_file():
    with pytest.raises(ProfileError) as exc:
        build_handlers([HandlerSpec(
            name="dskp", params={"mode": "static", "entries": [{"sheet": "ISNIN"}]})])
    assert "missing 'file'" in str(exc.value)


def test_dskp_selection_must_be_a_triple():
    with pytest.raises(ProfileError) as exc:
        build_handlers([HandlerSpec(
            name="dskp",
            params={"entries": [{"sheet": "ISNIN", "file": "t1.json",
                                 "selection": [1, 1]}]})])
    assert "'selection'" in str(exc.value)


def test_week_and_menu_accept_empty_params():
    build_handlers([HandlerSpec(name="week"), HandlerSpec(name="menu")])


# --- picking this week's workbook ({minggu} patterns + templates map) -----

def _week_profile(tmp_path, template, templates=None):
    """Profile whose inputs.template points inside tmp_path."""
    lines = [
        "profile: p",
        "inputs:",
        f'  template: "{template}"',
    ]
    if templates:
        lines.append("  templates:")
        lines += [f'    {k}: "{v}"' for k, v in templates.items()]
    lines.append("handlers: []")
    path = tmp_path / "profile.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return load_profile(str(path))


def test_template_placeholder_is_filled_from_the_week(tmp_path):
    (tmp_path / "M33.xlsx").write_bytes(b"x")
    profile = _week_profile(tmp_path, "M{minggu}.xlsx")
    assert resolve_template(profile, 33) == str(tmp_path / "M33.xlsx")


def test_template_pattern_searches_subdirectories(tmp_path):
    (tmp_path / "07. TMP-NEW").mkdir()
    (tmp_path / "07. TMP-NEW" / "M33.xlsx").write_bytes(b"x")
    profile = _week_profile(tmp_path, "*/M{minggu}.xlsx")
    assert resolve_template(profile, 33) == str(
        tmp_path / "07. TMP-NEW" / "M33.xlsx")


def test_templates_map_overrides_the_pattern(tmp_path):
    (tmp_path / "M33.xlsx").write_bytes(b"x")
    (tmp_path / "revisi.xlsx").write_bytes(b"x")
    profile = _week_profile(tmp_path, "M{minggu}.xlsx",
                            {"33": str(tmp_path / "revisi.xlsx")})
    assert resolve_template(profile, 33) == str(tmp_path / "revisi.xlsx")


def test_ambiguous_pattern_lists_the_candidates(tmp_path):
    for sub in ("06. JUNE", "07. TMP-NEW"):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "M18.xlsx").write_bytes(b"x")
    profile = _week_profile(tmp_path, "*/M{minggu}.xlsx")
    with pytest.raises(ProfileError) as exc:
        resolve_template(profile, 18)
    message = str(exc.value)
    assert "matches 2 workbooks" in message
    assert "06. JUNE" in message and "07. TMP-NEW" in message
    assert "inputs.templates" in message


def test_pattern_without_a_known_week_is_an_error(tmp_path):
    profile = _week_profile(tmp_path, "M{minggu}.xlsx")
    with pytest.raises(ProfileError) as exc:
        resolve_template(profile, None)
    assert "{minggu}" in str(exc.value)


def test_missing_workbook_is_an_error(tmp_path):
    profile = _week_profile(tmp_path, "M{minggu}.xlsx")
    with pytest.raises(ProfileError) as exc:
        resolve_template(profile, 34)
    assert "file not found" in str(exc.value)
    assert "M34.xlsx" in str(exc.value)


def test_pattern_that_matches_nothing_is_an_error(tmp_path):
    profile = _week_profile(tmp_path, "*/M{minggu}.xlsx")
    with pytest.raises(ProfileError) as exc:
        resolve_template(profile, 34)
    assert "no workbook matched" in str(exc.value)
    assert "minggu 34" in str(exc.value)


def test_plain_template_still_needs_no_week(tmp_path):
    (tmp_path / "template.xlsx").write_bytes(b"x")
    profile = _week_profile(tmp_path, "template.xlsx")
    assert resolve_template(profile, None) == str(tmp_path / "template.xlsx")


def test_templates_map_is_loaded_with_string_keys(tmp_path):
    profile = _week_profile(tmp_path, "M{minggu}.xlsx", {33: "m33.xlsx"})
    assert profile.inputs.templates == {"33": "m33.xlsx"}


def test_templates_map_rejects_a_bad_key(tmp_path):
    with pytest.raises(ProfileError) as exc:
        _week_profile(tmp_path, "M{minggu}.xlsx", {"minggu-33": "m33.xlsx"})
    assert "not a week number" in str(exc.value)
