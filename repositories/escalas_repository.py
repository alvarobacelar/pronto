from repositories.base import connect, logger
from repositories.errors import RepositoryError


def count_agendados_non_responsavel(area_id, data, turno):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(e.id) as count FROM escalas e
                JOIN voluntarios v ON e.voluntario_id = v.id
                WHERE e.area_id = %s AND e.data = %s AND e.turno = %s
                  AND (v.responsavel = 0 OR v.responsavel IS NULL)
                """,
                (area_id, data, turno),
            )
            row = cursor.fetchone() or {"count": 0}
            return row["count"]
    except Exception as err:
        logger.exception("Erro ao contar agendados: %s", err)
        raise RepositoryError("Erro ao validar vagas.") from err
    finally:
        conn.close()


def escala_exists(voluntario_id, data, turno):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM escalas
                WHERE voluntario_id = %s AND data = %s AND turno = %s
                """,
                (voluntario_id, data, turno),
            )
            return cursor.fetchone() is not None
    except Exception as err:
        logger.exception("Erro ao validar escala duplicada: %s", err)
        raise RepositoryError("Erro ao validar escala.") from err
    finally:
        conn.close()


def create_escala(voluntario_id, area_id, data, turno):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO escalas (voluntario_id, area_id, data, turno)
                VALUES (%s, %s, %s, %s)
                """,
                (voluntario_id, area_id, data, turno),
            )
        conn.commit()
    except Exception as err:
        conn.rollback()
        logger.exception("Erro ao criar escala: %s", err)
        raise RepositoryError("Erro ao salvar escala.") from err
    finally:
        conn.close()


def get_resumo_vagas(area_id, year, month):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT max_pessoas FROM areas WHERE id = %s", (area_id,))
            area = cursor.fetchone()
            if not area:
                return None, [], []

            params = (area_id, f"{year}-{month:02d}-%")
            cursor.execute(
                """
                SELECT e.data, e.turno, count(e.id) as total
                FROM escalas e
                JOIN voluntarios v ON e.voluntario_id = v.id
                WHERE e.area_id = %s AND e.data LIKE %s
                  AND (v.responsavel = 0 OR v.responsavel IS NULL)
                GROUP BY e.data, e.turno
                """,
                params,
            )
            agrupado = cursor.fetchall()

            cursor.execute(
                """
                SELECT e.data, e.turno, count(e.id) as total
                FROM escalas e
                JOIN voluntarios v ON e.voluntario_id = v.id
                WHERE e.area_id = %s AND e.data LIKE %s AND v.responsavel = 1
                GROUP BY e.data, e.turno
                """,
                params,
            )
            agrupado_responsavel = cursor.fetchall()
            return area["max_pessoas"], agrupado, agrupado_responsavel
    except Exception as err:
        logger.exception("Erro ao montar resumo de vagas: %s", err)
        raise RepositoryError("Erro ao gerar resumo de vagas.") from err
    finally:
        conn.close()


def get_dashboard_data(year, month, area_filter=None):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM areas")
            areas = cursor.fetchall()

            query = """
                SELECT e.id, v.nome as voluntario_nome, v.responsavel, e.area_id,
                       a.nome as area_nome, e.data, e.turno
                FROM escalas e
                JOIN voluntarios v ON e.voluntario_id = v.id
                JOIN areas a ON e.area_id = a.id
                WHERE e.data LIKE %s
            """
            params = [f"{year}-{month:02d}-%"]

            if area_filter:
                query += " AND e.area_id = %s"
                params.append(area_filter)

            query += " ORDER BY a.nome ASC, e.data ASC, e.turno ASC, v.responsavel DESC, v.nome ASC"
            cursor.execute(query, params)
            escalas = cursor.fetchall()
            return areas, escalas
    except Exception as err:
        logger.exception("Erro ao buscar dados de dashboard: %s", err)
        raise RepositoryError("Erro ao carregar dashboard.") from err
    finally:
        conn.close()


def delete_escala(escala_id):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM escalas WHERE id = %s", (escala_id,))
        conn.commit()
    except Exception as err:
        conn.rollback()
        logger.exception("Erro ao excluir escala: %s", err)
        raise RepositoryError("Erro ao excluir escala.") from err
    finally:
        conn.close()
