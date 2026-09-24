"""Ranse handlers: the handler protocol and the plugin registry.

``base.py`` is the contract every handler implements; ``loader.py`` builds
the registry from the plugins under ``./plugins`` (docs/DESIGN.md decision 2,
revised). The framework ships no handler of its own — a handler may call the
core write API and the readers, and core may never import one
(docs/DESIGN.md decision 6).
"""
