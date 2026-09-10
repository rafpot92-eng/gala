from contextlib import contextmanager

import psycopg2

from .config import settings


@contextmanager
def get_connection():
    with psycopg2.connect(settings.database_url) as conn:
        yield conn