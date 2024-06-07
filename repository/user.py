import os

def authenticate_user(user: str, password: str):
    registered_user = os.getenv("user")
    registered_password = os.getenv("password")
    valid_credentials = user == registered_user and password == registered_password
    return valid_credentials