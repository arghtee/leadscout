"""Target-role expansion into title variants (MCP-11)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

ROLE_VARIANTS: dict[str, tuple[str, ...]] = {
    "owner": (
        "owner",
        "co-owner",
        "proprietor",
        "founder",
        "co-founder",
        "managing director",
        "director",
    ),
    "founder": ("founder", "co-founder", "owner", "co-owner"),
    "managing director": ("managing director", "md", "ceo", "chief executive", "director"),
    "director": ("director", "managing director"),
    "marketing manager": (
        "marketing manager",
        "head of marketing",
        "marketing director",
        "marketing lead",
        "cmo",
    ),
}


@dataclass(frozen=True)
class RoleMatch:
    target: str
    variant: str


def _normalise(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9-]+", " ", text.lower()).split())


def expand_roles(targets: Sequence[str]) -> list[RoleMatch]:
    """Variants for each target role, most specific (longest) first within each target."""
    out: list[RoleMatch] = []
    for target in targets:
        key = _normalise(target)
        variants = ROLE_VARIANTS.get(key, (key,))
        out.extend(RoleMatch(target, v) for v in sorted(variants, key=len, reverse=True))
    return out


def match_role(title: str | None, targets: Sequence[str]) -> RoleMatch | None:
    if not title:
        return None
    norm = _normalise(title)
    for candidate in expand_roles(targets):
        if re.search(rf"(?<![\w-]){re.escape(candidate.variant)}(?![\w-])", norm):
            return candidate
    return None
