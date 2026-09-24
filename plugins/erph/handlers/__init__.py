"""erph handlers — one folder per handler, the folder name is the name.

The framework's plugin loader turns each subfolder into a registry entry
(``erph.handlers.<name>``, exactly one class carrying ``name`` and ``phase``),
so adding a handler here is the whole registration step. The shipped four are
indexed in the plugin's [`README.md`](../README.md).
"""
