from repositories.base import connect, logger
from repositories.errors import RepositoryError


def list_areas():
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM areas")
            return cursor.fetchall()
    except Exception as err:
        logger.exception("Erro ao listar áreas: %s", err)
        raise RepositoryError("Erro ao listar áreas.") from err
    finally:
        conn.close()


def get_area_by_id(area_id):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM areas WHERE id = %s", (area_id,))
            return cursor.fetchone()
    except Exception as err:
        logger.exception("Erro ao buscar área %s: %s", area_id, err)
        raise RepositoryError("Erro ao buscar área.") from err
    finally:
        conn.close()


def create_area(nome, max_pessoas):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO areas (nome, max_pessoas) VALUES (%s, %s)",
                (nome, int(max_pessoas)),
            )
        conn.commit()
    except Exception as err:
        conn.rollback()
        logger.exception("Erro ao criar área: %s", err)
        raise RepositoryError("Erro ao cadastrar área.") from err
    finally:
        conn.close()


def update_area(area_id, nome, max_pessoas):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE areas SET nome = %s, max_pessoas = %s WHERE id = %s",
                (nome, int(max_pessoas), area_id),
            )
        conn.commit()
    except Exception as err:
        conn.rollback()
        logger.exception("Erro ao atualizar área %s: %s", area_id, err)
        raise RepositoryError("Erro ao atualizar área.") from err
    finally:
        conn.close()


def delete_area(area_id):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM escalas WHERE area_id = %s", (area_id,))
            cursor.execute("DELETE FROM voluntario_areas WHERE area_id = %s", (area_id,))
            cursor.execute("DELETE FROM areas WHERE id = %s", (area_id,))
        conn.commit()
    except Exception as err:
        conn.rollback()
        logger.exception("Erro ao excluir área: %s", err)
        raise RepositoryError("Erro ao excluir área.") from err
    finally:
        conn.close()
