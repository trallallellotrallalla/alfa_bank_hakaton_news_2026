# db_client/config.py
import os
import psycopg2
from dotenv import load_dotenv

# Загружаем .env из корня проекта (на уровень выше папки db_client)
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path)

DB_USER = os.getenv("DB_USER", "arch")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "alfa_db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def get_connection():
    """Возвращает новое подключение к PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)