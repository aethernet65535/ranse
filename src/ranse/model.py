"""Profile model: the configuration the framework loads and hands around.

Deliberately neutral (docs/DESIGN.md S2): the framework knows a *profile* —
where the files are, which handlers to run and in what order — and nothing
about what any of it means. Types that carry business semantics belong to
the plugin that owns them (``plugins/<name>/domain.py``).
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class HandlerSpec:
    """One entry of the profile's explicit ``handlers:`` list."""

    name: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileInputs:
    """Profile ``inputs:`` — where the files live (decision 10/11).

    The framework itself knows two keys:

    ``template``   the workbook to fill; may contain ``{week}`` and/or glob
                   wildcards, so one profile can serve a whole year:
                   ``"…/2026/*/W{week}.xlsx"``;
    ``templates``  maps a published placeholder value to an explicit
                   workbook and wins over the pattern (escape hatch for
                   files that are named or placed differently).

    **Every other key is handler-specific**: it passes through verbatim into
    ``extra`` and is interpreted by the handler/reader that declares it —
    the same contract as handler ``params`` (docs/DESIGN.md S3.3: "every
    other key is handler-specific"). Use :meth:`get` to read one.
    """

    template: str
    templates: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, object] = field(default_factory=dict)

    def get(self, key, default=None):
        """One ``inputs:`` value by key — framework keys included.

        ``inputs.get("somekey")`` is what a handler whose profile key is
        ``somekey`` calls; ``template``/``templates`` resolve to the
        framework's own fields.
        """
        if key == "template":
            return self.template
        if key == "templates":
            return self.templates
        return self.extra.get(key, default)


@dataclass
class Profile:
    """A loaded profile file (docs/DESIGN.md S3: explicit handler list)."""

    name: str
    inputs: ProfileInputs
    context: dict = field(default_factory=dict)
    handlers: List[HandlerSpec] = field(default_factory=list)
    base_dir: str = ""
