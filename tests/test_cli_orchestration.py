"""Orchestrator declarations: requires-check + reader subcommand registry.

Both are framework mechanisms: the orchestrator only checks that each
declared context value exists (it never interprets the names), and the
reader subcommands are collected from the discovered plugins (decision 2,
revised).

The last block is the `ranse fill` option surface: the options are declared
by handlers, so the CLI scopes them to the handlers the profile names and
presents each handler as its own help section (docs/DESIGN.md S3.4).
"""

import argparse
import os
import textwrap
from types import SimpleNamespace

import pytest

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
    # opts in by having one of its readers declare a SUBCOMMAND spec.
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


# --- the `ranse fill` option surface (declared by handlers) ----------------

cli_options = fn("cli_options")
profile_handlers = fn("_profile_handlers")
main = fn("main")


def _profile(tmp_path, handlers):
    """A profile that names `handlers` (nothing else needs to exist)."""
    path = tmp_path / "profile.yaml"
    names = "".join(f"  - name: {name}\n" for name in handlers)
    path.write_text("profile: p\n"
                    "inputs: {template: t.xlsx}\n"
                    "handlers:\n" + names, encoding="utf-8")
    return path


def _fill_help(argv, capsys):
    """Run the CLI, expect argparse's --help exit, return what it printed."""
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0
    return capsys.readouterr().out


def test_cli_options_say_which_handler_declares_them():
    declared = {key: (handler, phase) for handler, phase, key, _, _ in
                cli_options()}
    assert declared["date"] == ("week", "resolve")
    assert declared["week"] == ("week", "resolve")
    assert declared["no_dskp_auto"] == ("dskp", "fill")


def test_cli_options_keep_the_order_they_are_asked_for():
    options = cli_options(["dskp", "week"])
    asked_order = list(dict.fromkeys(handler for handler, _, _, _, _ in options))
    assert asked_order == ["dskp", "week"]
    # An unknown name is skipped here; the profile loader reports it.
    assert cli_options(["not_a_handler"]) == []


def test_fill_help_without_a_profile_shows_every_handler(capsys):
    help_text = _fill_help(["fill", "--help"], capsys)
    assert "'week' handler (resolve):" in help_text
    assert "'dskp' handler (fill):" in help_text
    assert "--date DATE" in help_text and "--no-dskp-auto" in help_text


def test_fill_help_follows_the_profile(tmp_path, capsys):
    # The profile names dskp and week — in that order — and neither menu nor
    # fixed_cells, so the help shows exactly those two sections, in the
    # profile's order rather than by handler name.
    profile = _profile(tmp_path, ["dskp", "week"])
    help_text = _fill_help(["fill", "--profile", str(profile), "--help"],
                           capsys)
    assert "'dskp' handler (fill):" in help_text
    assert "'week' handler (resolve):" in help_text
    assert help_text.index("'dskp' handler") < help_text.index("'week' handler")


def test_fill_help_of_a_profile_without_handler_options(tmp_path, capsys):
    profile = _profile(tmp_path, ["menu", "fixed_cells"])
    help_text = _fill_help(["fill", "--profile", str(profile), "--help"],
                           capsys)
    assert help_text == textwrap.dedent("""\
        usage: ranse fill [-h] --profile PROFILE

        options:
          -h, --help         show this help message and exit
          --profile PROFILE  Path to the profile YAML (inputs + handlers)
        """)


def test_an_option_of_a_handler_the_profile_does_not_name_is_a_usage_error(
        tmp_path, capsys):
    profile = _profile(tmp_path, ["week", "menu"])
    with pytest.raises(SystemExit) as exc:
        main(["fill", "--profile", str(profile), "--no-dskp-auto"])
    assert exc.value.code == 2
    assert "--no-dskp-auto" in capsys.readouterr().err


def test_the_same_option_is_accepted_when_the_handler_is_named(tmp_path,
                                                               capsys):
    profile = _profile(tmp_path, ["week", "dskp"])
    with pytest.raises(SystemExit) as exc:
        main(["fill", "--profile", str(profile), "--no-dskp-auto"])
    # Not a usage error any more: it got past the parser and failed in the
    # run (the template does not exist).
    assert exc.value.code == 1
    assert "unrecognized arguments" not in capsys.readouterr().err


def test_profile_handlers_peek_only_reads_a_fill_profile(tmp_path):
    profile = _profile(tmp_path, ["week", "dskp"])
    assert profile_handlers(["fill", "--profile", str(profile)]) == [
        "week", "dskp"]
    assert profile_handlers(["fill", f"--profile={profile}"]) == [
        "week", "dskp"]
    # No profile to read, or a command that takes none: no scoping.
    assert profile_handlers(["fill", "--help"]) is None
    assert profile_handlers(["write", "--profile", str(profile)]) is None
    assert profile_handlers(["--help"]) is None
    # An unopenable path is left to the run, which reports it itself.
    assert profile_handlers(["fill", "--profile", "/nowhere/p.yaml"]) is None


def test_a_malformed_profile_reports_its_own_error(tmp_path, capsys):
    # Readable but malformed: the peek does not turn that into a fallback
    # option list — the CLI reports it the way a run would (exit 1).
    bad = tmp_path / "bad.yaml"
    bad.write_text("profile: p\nhandlers: []\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["fill", "--profile", str(bad), "--help"])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and "inputs" in err
