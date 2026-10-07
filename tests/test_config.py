from pathlib import Path

import pytest

from leadscout.config import Settings


def test_blank_env_values_fall_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A copied .env.example leaves optional numeric settings blank; that must not crash."""
    for name in ("MIN_CREDIT_BALANCE", "MAX_CREDITS_PER_RUN", "MAX_SPEND_PER_RUN"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("MAX_CONTACTS_PER_COMPANY", "3")
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.min_credit_balance is None
    assert settings.max_spend_per_run is None
    assert settings.max_contacts_per_company == 3
