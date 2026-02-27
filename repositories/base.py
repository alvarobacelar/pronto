import logging

from database import get_db_connection

logger = logging.getLogger(__name__)


def connect():
    conn = get_db_connection()
    if conn is None:
        from repositories.errors import RepositoryError

        raise RepositoryError("Erro ao conectar ao banco de dados.")
    return conn
