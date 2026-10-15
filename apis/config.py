import os

DEFAULT_PORTFOLIO_ORIGIN = "https://portfolio.gadcoder.com"


def portfolio_origins() -> list[str]:
    configured = os.getenv("PORTFOLIO_ORIGINS")
    source = configured if configured is not None else DEFAULT_PORTFOLIO_ORIGIN
    return [origin.strip().rstrip("/") for origin in source.split(",") if origin.strip()]
