"""Profile schema: explicit handlers, unknown names, param validation.

Stage 3 acceptance (PLAN.md §4): the three failure modes the registry owns —
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
