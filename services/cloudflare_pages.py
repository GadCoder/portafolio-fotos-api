import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


HOOK_ENV = "CLOUDFLARE_PAGES_DEPLOY_HOOK_URL"
HOOK_TIMEOUT_SECONDS = 15


class DeployHookNotConfigured(RuntimeError):
    """The deploy hook is missing or is not a trusted Cloudflare URL."""


class DeployHookError(RuntimeError):
    """Cloudflare did not accept the deployment request."""


def _configured_hook_url() -> str:
    hook_url = os.getenv(HOOK_ENV, "").strip()
    if not hook_url:
        raise DeployHookNotConfigured

    try:
        parsed = urlsplit(hook_url)
        trusted_url = (
            parsed.scheme == "https"
            and parsed.hostname == "api.cloudflare.com"
            and parsed.path.startswith("/client/v4/pages/webhooks/deploy_hooks/")
            and bool(parsed.path.rsplit("/", 1)[-1])
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and not parsed.fragment
        )
    except ValueError:
        trusted_url = False

    if not trusted_url:
        raise DeployHookNotConfigured
    return hook_url


def trigger_deploy() -> None:
    hook_url = _configured_hook_url()
    request = Request(hook_url, method="POST")
    try:
        with urlopen(request, timeout=HOOK_TIMEOUT_SECONDS) as response:
            if not 200 <= response.status < 300:
                raise DeployHookError("Cloudflare Pages deployment request failed")
    except (HTTPError, URLError, TimeoutError, OSError):
        raise DeployHookError("Cloudflare Pages deployment request failed") from None
