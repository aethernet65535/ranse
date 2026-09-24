"""Plugin discovery: one ``./plugins`` directory, one package per business.

A *plugin* is a Python package sitting in ``./plugins`` and following a fixed
folder convention — ``handlers/<name>/`` is a handler, ``inputs/<name>/`` is
a reader. There is no manifest and no entry point: the folder **is** the
registration (docs/DESIGN.md D2, revised from "built-in registry" to "local
directory scan").

This module is the only framework code that puts a directory on ``sys.path``
and imports a plugin; everything above it (the handler loader, the CLI)
works with the plain names it returns. It knows nothing about what any
plugin means.

The search roots mirror the input-path fallback in :func:`ranse.inputs.yaml.
input_bases`: ``./plugins`` in the current directory first, then — **only in
a source checkout** — the repository root's ``plugins/``. An installed
package contributes no root, so it looks for plugins beside the project it
is run against instead of guessing.
"""

import importlib
import os
import re
import sys

from . import _IS_SOURCE_CHECKOUT, _REPO_ROOT
from .errors import ProfileError

PLUGINS_DIRNAME = "plugins"

# What a subfolder of a plugin means, and the noun used in error messages.
_KINDS = {"handlers": "handler", "inputs": "reader"}

# A plugin folder name must be a legal snake_case package name.
_PACKAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def search_roots():
    """The directories a plugin may live in, in resolution order."""
    roots = [os.path.abspath(PLUGINS_DIRNAME)]
    if _IS_SOURCE_CHECKOUT:
        checkout = os.path.join(_REPO_ROOT, PLUGINS_DIRNAME)
        if checkout not in roots:
            roots.append(checkout)
    return roots


def has_plugins():
    """Is there a ``plugins`` directory to scan at all?"""
    return any(os.path.isdir(root) for root in search_roots())


def plugin_packages():
    """The plugin package names found under the search roots, in order."""
    names = []
    for root in search_roots():
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            if not _is_package(os.path.join(root, entry)):
                continue
            if entry not in names:
                names.append(entry)
    return names


def discovered(kind):
    """``{name: module}`` for every ``<plugin>/<kind>/<name>/`` package.

    ``kind`` is ``"handlers"`` or ``"inputs"``. Two plugins declaring the
    same name is a conflict: it would make the profile ambiguous, so it
    fails here, listing both sources.
    """
    if kind not in _KINDS:
        raise ValueError(f"unknown plugin kind: {kind!r}")

    _bootstrap()

    found = {}
    sources = {}
    for plugin in plugin_packages():
        for root in search_roots():
            base = os.path.join(root, plugin, kind)
            if not os.path.isdir(base):
                continue
            for name in sorted(os.listdir(base)):
                if not _is_package(os.path.join(base, name)):
                    continue
                if name in found:
                    raise ProfileError(
                        f"duplicate {_KINDS[kind]} name {name!r}: declared by "
                        f"both plugin {sources[name]!r} and plugin "
                        f"{plugin!r}")
                sources[name] = plugin
                found[name] = importlib.import_module(
                    f"{plugin}.{kind}.{name}")
    return found


def reader_subcommands():
    """The subcommand specs the discovered readers declare.

    A reader that wants a top-level CLI command defines ``SUBCOMMAND`` —
    spec ``{"name", "help", "add_arguments", "run"}``. Nothing ships one, so
    the stock CLI stays framework-only (decision 2).
    """
    specs = []
    for module in discovered("inputs").values():
        spec = getattr(module, "SUBCOMMAND", None)
        if spec is not None:
            specs.append(spec)
    return tuple(specs)


def _is_package(path):
    """Is ``path`` a snake_case package folder (i.e. does it register)?"""
    return (os.path.isdir(path)
            and _PACKAGE_NAME_RE.match(os.path.basename(path)) is not None
            and os.path.isfile(os.path.join(path, "__init__.py")))


def _bootstrap():
    """Put the search roots on ``sys.path`` so plugin packages import."""
    for root in reversed(search_roots()):
        if root not in sys.path:
            sys.path.insert(0, root)
