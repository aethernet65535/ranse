"""Plugin discovery: the folder convention, conflicts and the error prompts.

The mechanism replaced the built-in registries (docs/DESIGN.md D2, revised),
so its rules are contract: ``plugins/<pkg>/handlers/<name>/`` registers a
handler, ``plugins/<pkg>/inputs/<name>/`` registers a reader, a name declared
twice fails at load time, and an unresolvable handler name says what was
found (or that there are no plugins at all).
"""

import os
import sys

import pytest

from harness import PLUGINS_DIR, PLUGIN_DIR, fn

build_handlers = fn("build_handlers")
handlers = fn("handlers")
discovered = fn("discovered")
has_plugins = fn("has_plugins")
reader_subcommands = fn("reader_subcommands")
HandlerSpec = fn("HandlerSpec")
ProfileError = fn("ProfileError")

# The plugin-scan module, however the framework happens to name it.
PLUGIN_SCAN = sys.modules[has_plugins.__module__]

# The handlers the shipped plugin declares (folder name → phase).
SHIPPED = {"week": "resolve", "menu": "fill", "fixed_cells": "fill",
           "dskp": "fill"}


def _write_package(path, body=""):
    path.mkdir(parents=True, exist_ok=True)
    (path / "__init__.py").write_text(body, encoding="utf-8")


def _plugin_with_handler(root, plugin, name):
    """A minimal plugin tree: <root>/<plugin>/handlers/<name>/."""
    _write_package(root / plugin)
    _write_package(root / plugin / "handlers")
    _write_package(root / plugin / "handlers" / name)


def _plugin_with_reader(root, plugin, name, body=""):
    """A minimal plugin tree: <root>/<plugin>/inputs/<name>/."""
    _write_package(root / plugin)
    _write_package(root / plugin / "inputs")
    _write_package(root / plugin / "inputs" / name, body)


# --- the shipped plugin ----------------------------------------------------

def test_the_shipped_handlers_are_discovered_from_the_plugins_folder():
    assert PLUGINS_DIR.is_dir()
    assert sorted(discovered("handlers")) == sorted(SHIPPED)
    assert sorted(handlers()) == sorted(SHIPPED)


def test_discovered_handlers_carry_the_folder_name_and_a_phase():
    for name, cls in handlers().items():
        assert cls.name == name
        assert cls.phase == SHIPPED[name]


def test_the_shipped_readers_are_discovered_and_declare_no_subcommand():
    assert sorted(discovered("inputs")) == ["calendar", "dskp", "timetable"]
    assert reader_subcommands() == ()


def test_the_shipped_plugin_is_a_package_under_plugins():
    assert (PLUGIN_DIR / "__init__.py").is_file()
    assert (PLUGIN_DIR / "README.md").is_file()


# --- the search roots ------------------------------------------------------

def test_search_roots_start_with_the_current_directory():
    roots = PLUGIN_SCAN.search_roots()
    assert roots[0] == os.path.abspath("plugins")
    assert has_plugins() is True


def test_no_plugins_directory_is_a_neutral_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(PLUGIN_SCAN, "search_roots",
                        lambda: [str(tmp_path / "nowhere")])
    assert has_plugins() is False
    with pytest.raises(ProfileError) as exc:
        build_handlers([HandlerSpec(name="week")])
    message = str(exc.value)
    assert "unknown handler 'week'" in message
    assert "no plugins found under ./plugins" in message
    assert "available" not in message


def test_unknown_handler_lists_the_discovered_names():
    with pytest.raises(ProfileError) as exc:
        build_handlers([HandlerSpec(name="not_a_handler")])
    message = str(exc.value)
    assert "unknown handler 'not_a_handler'" in message
    for name in SHIPPED:
        assert name in message


# --- conflicts and conventions ---------------------------------------------

def test_the_same_handler_name_in_two_plugins_is_a_conflict(tmp_path,
                                                            monkeypatch):
    _plugin_with_handler(tmp_path, "plugin_one", "shared")
    _plugin_with_handler(tmp_path, "plugin_two", "shared")
    monkeypatch.setattr(PLUGIN_SCAN, "search_roots", lambda: [str(tmp_path)])

    with pytest.raises(ProfileError) as exc:
        discovered("handlers")
    message = str(exc.value)
    assert "duplicate handler name 'shared'" in message
    assert "plugin_one" in message and "plugin_two" in message


def test_a_folder_that_is_not_a_snake_case_package_is_ignored(tmp_path,
                                                              monkeypatch):
    _write_package(tmp_path / "plugin_ok" / "handlers" / "good")
    _plugin_with_handler(tmp_path, "plugin_ok", "Bad-Name")
    (tmp_path / "plugin_ok" / "handlers" / "not_a_package").mkdir()
    monkeypatch.setattr(PLUGIN_SCAN, "search_roots", lambda: [str(tmp_path)])

    assert sorted(discovered("handlers")) == ["good"]


def test_a_handler_folder_must_package_one_matching_class(tmp_path,
                                                          monkeypatch):
    _plugin_with_handler(tmp_path, "plugin_bad", "lonely")
    monkeypatch.setattr(PLUGIN_SCAN, "search_roots", lambda: [str(tmp_path)])

    with pytest.raises(ProfileError) as exc:
        handlers()
    assert "must define exactly one class" in str(exc.value)


# --- reader subcommands ----------------------------------------------------

def test_a_reader_may_declare_a_subcommand(tmp_path, monkeypatch):
    spec = {"name": "fakecmd", "help": "…"}
    _plugin_with_reader(tmp_path, "plugin_cli", "fake",
                        f"SUBCOMMAND = {spec!r}\n")
    monkeypatch.setattr(PLUGIN_SCAN, "search_roots", lambda: [str(tmp_path)])

    assert reader_subcommands() == (spec,)
