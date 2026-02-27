import pymysql

from repositories.base import connect, logger
from repositories.errors import DuplicatePhoneError, RepositoryError


def get_voluntario_by_phone(telefone):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM voluntarios WHERE telefone = %s", (telefone,))
            return cursor.fetchone()
    except Exception as err:
        logger.exception("Erro ao buscar voluntário por telefone: %s", err)
        raise RepositoryError("Erro ao buscar voluntário.") from err
    finally:
        conn.close()


def get_voluntario_by_id(voluntario_id):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM voluntarios WHERE id = %s", (voluntario_id,))
            return cursor.fetchone()
    except Exception as err:
        logger.exception("Erro ao buscar voluntário %s: %s", voluntario_id, err)
        raise RepositoryError("Erro ao buscar voluntário.") from err
    finally:
        conn.close()


def voluntario_has_area(voluntario_id, area_id):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM voluntario_areas WHERE voluntario_id = %s AND area_id = %s",
                (voluntario_id, area_id),
            )
            return cursor.fetchone() is not None
    except Exception as err:
        logger.exception("Erro ao validar área do voluntário: %s", err)
        raise RepositoryError("Erro ao validar área do voluntário.") from err
    finally:
        conn.close()


def get_voluntario_with_areas_by_phone(telefone):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome FROM voluntarios WHERE telefone = %s", (telefone,))
            voluntario = cursor.fetchone()
            if not voluntario:
                return None, []

            cursor.execute(
                """
                SELECT a.id, a.nome
                FROM areas a
                JOIN voluntario_areas va ON a.id = va.area_id
                WHERE va.voluntario_id = %s
                """,
                (voluntario["id"],),
            )
            areas = cursor.fetchall()
            return voluntario, areas
    except Exception as err:
        logger.exception("Erro ao buscar áreas do voluntário: %s", err)
        raise RepositoryError("Erro ao buscar áreas do voluntário.") from err
    finally:
        conn.close()


def list_voluntarios_with_areas():
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT v.*, GROUP_CONCAT(a.nome SEPARATOR ', ') as areas_nomes
                FROM voluntarios v
                LEFT JOIN voluntario_areas va ON v.id = va.voluntario_id
                LEFT JOIN areas a ON va.area_id = a.id
                GROUP BY v.id
                ORDER BY v.responsavel DESC, v.nome ASC
                """
            )
            voluntarios = cursor.fetchall()

            cursor.execute("SELECT * FROM areas ORDER BY nome ASC")
            areas = cursor.fetchall()
            return voluntarios, areas
    except Exception as err:
        logger.exception("Erro ao listar voluntários: %s", err)
        raise RepositoryError("Erro ao listar voluntários.") from err
    finally:
        conn.close()


def create_voluntario(nome, telefone, responsavel, areas_selecionadas):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO voluntarios (nome, telefone, responsavel) VALUES (%s, %s, %s)",
                (nome, telefone, responsavel),
            )
            voluntario_id = cursor.lastrowid

            for area_id in areas_selecionadas:
                cursor.execute(
                    "INSERT INTO voluntario_areas (voluntario_id, area_id) VALUES (%s, %s)",
                    (voluntario_id, int(area_id)),
                )
        conn.commit()
    except pymysql.IntegrityError as err:
        conn.rollback()
        logger.warning("Telefone duplicado ao criar voluntário: %s", err)
        raise DuplicatePhoneError("Telefone já cadastrado.") from err
    except Exception as err:
        conn.rollback()
        logger.exception("Erro ao criar voluntário: %s", err)
        raise RepositoryError("Erro ao cadastrar voluntário.") from err
    finally:
        conn.close()


def delete_voluntario(voluntario_id):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM escalas WHERE voluntario_id = %s", (voluntario_id,))
            cursor.execute("DELETE FROM voluntario_areas WHERE voluntario_id = %s", (voluntario_id,))
            cursor.execute("DELETE FROM voluntarios WHERE id = %s", (voluntario_id,))
        conn.commit()
    except Exception as err:
        conn.rollback()
        logger.exception("Erro ao excluir voluntário: %s", err)
        raise RepositoryError("Erro ao excluir voluntário.") from err
    finally:
        conn.close()


def get_voluntario_area_ids(voluntario_id):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT area_id FROM voluntario_areas WHERE voluntario_id = %s", (voluntario_id,))
            rows = cursor.fetchall()
            return [row["area_id"] for row in rows]
    except Exception as err:
        logger.exception("Erro ao buscar áreas do voluntário %s: %s", voluntario_id, err)
        raise RepositoryError("Erro ao buscar áreas do voluntário.") from err
    finally:
        conn.close()


def update_voluntario(voluntario_id, nome, telefone, responsavel, areas_selecionadas):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE voluntarios SET nome = %s, telefone = %s, responsavel = %s WHERE id = %s",
                (nome, telefone, responsavel, voluntario_id),
            )
            cursor.execute("DELETE FROM voluntario_areas WHERE voluntario_id = %s", (voluntario_id,))

            for area_id in areas_selecionadas:
                cursor.execute(
                    "INSERT INTO voluntario_areas (voluntario_id, area_id) VALUES (%s, %s)",
                    (voluntario_id, int(area_id)),
                )
        conn.commit()
    except pymysql.IntegrityError as err:
        conn.rollback()
        logger.warning("Telefone duplicado ao atualizar voluntário: %s", err)
        raise DuplicatePhoneError("Telefone já cadastrado por outro voluntário.") from err
    except Exception as err:
        conn.rollback()
        logger.exception("Erro ao atualizar voluntário: %s", err)
        raise RepositoryError("Erro ao atualizar voluntário.") from err
    finally:
        conn.close()


def list_inativos(data_limite_iso):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT v.id, v.nome, v.telefone, v.responsavel,
                       (SELECT MAX(e.data) FROM escalas e WHERE e.voluntario_id = v.id) as ultima_escala
                FROM voluntarios v
                WHERE v.id NOT IN (
                    SELECT DISTINCT voluntario_id
                    FROM escalas
                    WHERE data >= %s
                )
                ORDER BY ultima_escala DESC, v.nome ASC
                """,
                (data_limite_iso,),
            )
            return cursor.fetchall()
    except Exception as err:
        logger.exception("Erro ao listar inativos: %s", err)
        raise RepositoryError("Erro ao listar inativos.") from err
    finally:
        conn.close()
