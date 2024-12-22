import os
from settings import settings


def authenticate_user(user: str, password: str):
    print(f"User: {user}, Password: {password}")
    print(f"Settings user: {settings.user}, Settings password: {settings.password}")
    valid_credentials = (
        str(user) == settings.user and str(password) == settings.password
    )
    return valid_credentials
