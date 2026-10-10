from fastapi.templating import Jinja2Templates
from typing import Any


templates = Jinja2Templates(directory="templates")


def get_login_page(context: dict[str, Any]):
    return templates.TemplateResponse(
        request=context["request"], name="login.html", context=context
    )


def get_main_page(context: dict[str, Any]):
    return templates.TemplateResponse(
        request=context["request"], name="index.html", context=context
    )


def get_unauthorized_page(context: dict[str, Any]):
    return templates.TemplateResponse(
        request=context["request"], name="unauthorized.html", context=context
    )
