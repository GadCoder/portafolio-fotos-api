from fastapi import APIRouter

from apis.routes import route_photo, route_html, route_admin_api, route_series

api_router = APIRouter()

api_router.include_router(route_photo.router, prefix="/photo", tags=["photo"])
api_router.include_router(route_html.router, tags=["html"])
api_router.include_router(route_series.router)
api_router.include_router(route_admin_api.router)
