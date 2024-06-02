import os

# Example using environment variables
DATABASE_USERNAME = os.getenv("MYSQL_USER", "root")
DATABASE_PASSWORD = os.getenv("MYSQL_PASSWORD", "your_password")
DATABASE_HOST = "db"
DATABASE_PORT = 3306
DATABASE_NAME = os.getenv("MYSQL_DATABASE", "your_database")

DATABASE_URL = f"mysql+pymysql://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
