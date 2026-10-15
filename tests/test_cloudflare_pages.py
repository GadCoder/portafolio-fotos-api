from email.message import Message
from urllib.error import HTTPError
from unittest.mock import Mock

import pytest

import services.cloudflare_pages as cloudflare_pages


HOOK_URL = "https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/private-hook"


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_trigger_posts_to_configured_cloudflare_hook(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_PAGES_DEPLOY_HOOK_URL", HOOK_URL)
    urlopen = Mock(return_value=FakeResponse())
    monkeypatch.setattr(cloudflare_pages, "urlopen", urlopen)

    cloudflare_pages.trigger_deploy()

    request = urlopen.call_args.args[0]
    assert request.full_url == HOOK_URL
    assert request.method == "POST"
    assert request.data is None
    assert urlopen.call_args.kwargs["timeout"] == 15


def test_trigger_fails_closed_when_hook_is_missing(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_PAGES_DEPLOY_HOOK_URL", raising=False)
    with pytest.raises(cloudflare_pages.DeployHookNotConfigured):
        cloudflare_pages.trigger_deploy()


def test_trigger_rejects_non_cloudflare_or_non_https_urls(monkeypatch):
    for url in (
        "http://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/hook",
        "https://attacker.example/hook",
        "https://api.cloudflare.com/client/v4/accounts/account-id",
    ):
        monkeypatch.setenv("CLOUDFLARE_PAGES_DEPLOY_HOOK_URL", url)
        with pytest.raises(cloudflare_pages.DeployHookNotConfigured):
            cloudflare_pages.trigger_deploy()


def test_trigger_hides_hook_url_when_cloudflare_rejects_request(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_PAGES_DEPLOY_HOOK_URL", HOOK_URL)
    urlopen = Mock(side_effect=HTTPError(HOOK_URL, 503, "upstream failure", Message(), None))
    monkeypatch.setattr(cloudflare_pages, "urlopen", urlopen)

    with pytest.raises(cloudflare_pages.DeployHookError) as error:
        cloudflare_pages.trigger_deploy()

    assert "private-hook" not in str(error.value)
    assert HOOK_URL not in str(error.value)
