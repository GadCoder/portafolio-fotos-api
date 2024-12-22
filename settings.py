import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    DATABASE_USERNAME = os.getenv("MYSQL_USER", "root")
    DATABASE_PASSWORD = os.getenv("MYSQL_PASSWORD", "your_password")
    DATABASE_HOST = os.getenv("MYSQL_HOST", "localhost")
    DATABASE_PORT = 3306
    DATABASE_NAME = os.getenv("MYSQL_DATABASE", "your_database")
    DATABASE_URL = f"mysql+mysqlconnector://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"

    user = os.getenv("user")
    password = os.getenv("password")


settings = Settings()
