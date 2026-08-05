import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


class Config:
    DB_SERVER = os.environ["DB_SERVER"]
    DB_PORT = int(os.environ.get("DB_PORT", 1433))
    DB_NAME = os.environ["DB_NAME"]
    DB_USER = os.environ["DB_USER"]
    DB_PASSWORD = os.environ["DB_PASSWORD"]

    SECRET_KEY = os.environ["APP_SECRET_KEY"]
    EMPLOYEE_USERNAME = os.environ["EMPLOYEE_USERNAME"]
    EMPLOYEE_PASSWORD_HASH = os.environ["EMPLOYEE_PASSWORD_HASH"]
    MANAGER_USERNAME = os.environ["MANAGER_USERNAME"]
    MANAGER_PASSWORD_HASH = os.environ["MANAGER_PASSWORD_HASH"]
