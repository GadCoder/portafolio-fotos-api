import os
from dotenv import load_dotenv
from pathlib import Path


env_path = Path("") / ".env"
load_dotenv(dotenv_path=env_path)

# Example using environment variables
DATABASE_USERNAME = os.getenv("MYSQL_USER", "root")
DATABASE_PASSWORD = os.getenv("MYSQL_PASSWORD", "your_password")
DATABASE_HOST = os.getenv("MYSQL_HOST", "localhost")
DATABASE_PORT = 3306
DATABASE_NAME = os.getenv("MYSQL_DATABASE", "your_database")

DATABASE_URL = f"mysql+mysqlconnector://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
