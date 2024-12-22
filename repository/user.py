import os
from settings import settings


def authenticate_user(user: str, password: str):
    valid_credentials = (
        str(user) == settings.user and str(password) == settings.password
    )
    return valid_credentials
