from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any


templates = Jinja2Templates(directory="templates")


@lru_cache
def static_asset_version(path: str) -> str:
    # Assets are immutable for the lifetime of a deployed server process.
    asset = Path(__file__).resolve().parent.parent / "static" / path.lstrip("/")
    return sha256(asset.read_bytes()).hexdigest()[:12]


def static_asset_url(request: Request, path: str) -> str:
    return f"{request.url_for('static', path=path)}?v={static_asset_version(path)}"


templates.env.globals["static_asset_url"] = static_asset_url


def get_login_page(context: dict[str, Any]):
    return templates.TemplateResponse(
        request=context["request"], name="login.html", context=context
    )


def get_main_page(context: dict[str, Any]):
    return templates.TemplateResponse(
        request=context["request"], name="index.html", context=context
    )


def get_photo_edit_page(context: dict[str, Any]):
    return templates.TemplateResponse(
        request=context["request"], name="photo_edit.html", context=context
    )


def get_unauthorized_page(context: dict[str, Any]):
    return templates.TemplateResponse(
        request=context["request"], name="unauthorized.html", context=context
    )
