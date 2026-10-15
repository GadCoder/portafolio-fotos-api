from apis.config import DEFAULT_PORTFOLIO_ORIGIN, portfolio_origins


def test_portfolio_origins_uses_default_when_unconfigured(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_ORIGINS", raising=False)

    assert portfolio_origins() == [DEFAULT_PORTFOLIO_ORIGIN]


def test_portfolio_origins_normalizes_configured_values(monkeypatch):
    monkeypatch.setenv(
        "PORTFOLIO_ORIGINS",
        "https://admin.example, https://portfolio.example/,,",
    )

    assert portfolio_origins() == [
        "https://admin.example",
        "https://portfolio.example",
    ]
