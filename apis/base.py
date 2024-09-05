from fastapi import APIRouter

from apis.routes import route_photo, route_html

api_router = APIRouter()

api_router.include_router(route_photo.router, prefix="/photo", tags=["photo"])
api_router.include_router(route_html.router, tags=["html"])
