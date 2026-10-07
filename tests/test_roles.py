import pytest

from leadscout.qualification.roles import expand_roles, match_role


@pytest.mark.parametrize(
    ("title", "target", "variant"),
    [
        ("Owner", "owner", "owner"),
        ("Co-Founder & Head Chef", "owner", "co-founder"),
        ("Managing Director", "owner", "managing director"),
        ("Proprietor", "owner", "proprietor"),
        ("Head of Marketing", "marketing manager", "head of marketing"),
    ],
)
def test_match_role_records_variant(title: str, target: str, variant: str) -> None:
    match = match_role(title, ["owner", "marketing manager"])
    assert match is not None
    assert (match.target, match.variant) == (target, variant)


@pytest.mark.parametrize("title", [None, "", "Barista", "Shop Floor Assistant", "Co-ordinator"])
def test_match_role_rejects(title: str | None) -> None:
    assert match_role(title, ["owner", "marketing manager"]) is None


def test_unknown_target_matches_itself() -> None:
    assert [m.variant for m in expand_roles(["Head Chef"])] == ["head chef"]
    assert match_role("Executive Head Chef", ["Head Chef"]) is not None
