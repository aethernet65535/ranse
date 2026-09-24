"""Orchestrator declarations: requires-check + reader subcommand registry.

Both are framework mechanisms: the orchestrator only checks that each
declared context value exists (it never interprets the names), and the
reader registry is a static list the readers declare into (decision 2).
"""

import argparse
import os
from types import SimpleNamespace

from harness import call_error, fn

require_something_to_do = fn("_require_something_to_do")
Context = fn("Context")
Profile = fn("Profile")
ProfileInputs = fn("ProfileInputs")
WeekResolver = fn("WeekResolver")
subcommands = fn("subcommands")


def _ctx(**fields):
    ctx = Context(
        profile=Profile(name="p", inputs=ProfileInputs(template="t.xlsx")))
    for key, value in fields.items():
        setattr(ctx, key, value)
    return ctx


def _filler(name, requires=()):
    return SimpleNamespace(name=name, phase="fill", requires=requires)


# --- _require_something_to_do ----------------------------------------------

def test_every_filler_blocked_is_an_error():
    handlers = [(None, _filler("menu", ("schedule",)))]
    msg = call_error(require_something_to_do, argparse.ArgumentParser(prog="ranse"),
                     handlers, _ctx())
    assert "nothing to do" in msg
    assert "schedule" in msg


def test_one_unblocked_filler_keeps_the_run():
    handlers = [(None, _filler("menu", ("schedule",))),
                (None, _filler("dskp"))]
    require_something_to_do(argparse.ArgumentParser(), handlers, _ctx())


def test_a_published_value_unblocks_the_filler():
    handlers = [(None, _filler("menu", ("schedule",)))]
    require_something_to_do(argparse.ArgumentParser(), handlers,
                             _ctx(schedule=object()))


def test_no_fill_handler_is_reported():
    handlers = [(None, SimpleNamespace(name="week", phase="resolve"))]
    msg = call_error(require_something_to_do, argparse.ArgumentParser(prog="ranse"),
                     handlers, _ctx())
    assert "no fill handler is configured" in msg


# --- template_vars published by the week resolver ---------------------------

def test_week_resolver_publishes_the_week_for_the_template():
    ctx = _ctx(runtime={"date": "2026-09-20", "week": 33})
    WeekResolver().resolve(ctx)
    assert ctx.template_vars == {"week": 33}


def test_week_resolver_publishes_nothing_without_a_calendar():
    ctx = _ctx(runtime={"date": "2026-09-20"})
    WeekResolver().resolve(ctx)
    assert ctx.template_vars == {}


# --- reader subcommand registry --------------------------------------------

build_parser = fn("_build_parser")


def test_the_shipped_registry_is_empty():
    # The top-level CLI ships only the framework's fill/write; a business
    # opts in by listing its reader in `inputs._READERS`.
    assert subcommands() == ()


def test_top_level_help_lists_only_framework_commands():
    help_text = build_parser({}).format_help()
    assert "{fill,write}" in help_text
    assert "fill the profile's template" in help_text
    assert "dskp" not in help_text.lower()


# --- path bases (Phase 5: one builder, checkout-guarded repo fallback) -----

input_bases = fn("input_bases")


def test_input_bases_put_the_profile_folder_first():
    profile = Profile(name="p", inputs=ProfileInputs(template="t.xlsx"),
                      base_dir="/profiles/p")
    bases = input_bases(profile)
    assert bases[0] == "/profiles/p"
    assert bases[1] == os.getcwd()


def test_input_bases_accept_an_extra_first_base():
    assert input_bases(first="/data")[0] == "/data"
    assert input_bases(first="/data")[1] == os.getcwd()


def test_repo_root_fallback_only_in_a_source_checkout():
    from ranse import _IS_SOURCE_CHECKOUT, _REPO_ROOT
    bases = input_bases()
    assert _REPO_ROOT in bases
    # This test suite runs from a source checkout, so the fallback is on;
    # an installed wheel turns it off (no pyproject/src beside the package).
    assert _IS_SOURCE_CHECKOUT is True
    assert bases[-1] == _REPO_ROOT
