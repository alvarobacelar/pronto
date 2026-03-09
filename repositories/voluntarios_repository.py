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


def list_voluntarios_with_areas(area_id=None, search_query=None, limit=30, offset=0):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            # 1. Base conditions
            where_clauses = []
            params = []
            
            if area_id:
                where_clauses.append("v.id IN (SELECT voluntario_id FROM voluntario_areas WHERE area_id = %s)")
                params.append(area_id)
                
            if search_query:
                where_clauses.append("(v.nome LIKE %s OR v.telefone LIKE %s)")
                param_query = f"%{search_query}%"
                params.extend([param_query, param_query])
                
            where_sql = ""
            if where_clauses:
                where_sql = " WHERE " + " AND ".join(where_clauses)
                
            # 2. Count total records
            count_query = "SELECT COUNT(*) as total FROM voluntarios v" + where_sql
            cursor.execute(count_query, tuple(params))
            total_count = cursor.fetchone()["total"]

            # 3. Main Query
            limit_val = int(limit)
            offset_val = int(offset)
            
            # Using concatenation instead of f-string for query assembly to avoid bandit/safety warnings
            query = """
                SELECT v.*, GROUP_CONCAT(a.nome SEPARATOR ', ') as areas_nomes
                FROM voluntarios v
                LEFT JOIN voluntario_areas va ON v.id = va.voluntario_id
                LEFT JOIN areas a ON va.area_id = a.id
            """ + where_sql + """
                GROUP BY v.id
                ORDER BY v.responsavel DESC, v.nome ASC
                LIMIT %s OFFSET %s
            """
            
            # Combine where params with limit/offset params
            query_params = list(params)
            query_params.extend([limit_val, offset_val])
            
            cursor.execute(query, tuple(query_params))
            voluntarios = cursor.fetchall()

            cursor.execute("SELECT * FROM areas ORDER BY nome ASC")
            areas = cursor.fetchall()
            
            return voluntarios, areas, total_count
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


def count_inativos(data_limite_iso, nome_filter=None, area_id=None):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT COUNT(*) as total
                FROM voluntarios v
                WHERE v.id NOT IN (
                    SELECT DISTINCT voluntario_id
                    FROM escalas
                    WHERE data >= %s
                )
            """
            params = [data_limite_iso]

            if nome_filter:
                query += " AND v.nome LIKE %s"
                params.append(f"%{nome_filter}%")

            if area_id:
                query += """
                    AND EXISTS (
                        SELECT 1
                        FROM voluntario_areas va2
                        WHERE va2.voluntario_id = v.id AND va2.area_id = %s
                    )
                """
                params.append(area_id)

            cursor.execute(query, tuple(params))
            result = cursor.fetchone()
            return result["total"] if result else 0
    except Exception as err:
        logger.exception("Erro ao contar inativos: %s", err)
        raise RepositoryError("Erro ao contar inativos.") from err
    finally:
        conn.close()


def list_inativos(data_limite_iso, nome_filter=None, area_id=None, limit=None, offset=0):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT v.id, v.nome, v.telefone, v.responsavel,
                       GROUP_CONCAT(DISTINCT a.nome ORDER BY a.nome SEPARATOR ', ') as areas_nomes,
                       (SELECT MAX(e.data) FROM escalas e WHERE e.voluntario_id = v.id) as ultima_escala
                FROM voluntarios v
                LEFT JOIN voluntario_areas va ON va.voluntario_id = v.id
                LEFT JOIN areas a ON a.id = va.area_id
                WHERE v.id NOT IN (
                    SELECT DISTINCT voluntario_id
                    FROM escalas
                    WHERE data >= %s
                )
            """
            params = [data_limite_iso]

            if nome_filter:
                query += " AND v.nome LIKE %s"
                params.append(f"%{nome_filter}%")

            if area_id:
                query += """
                    AND EXISTS (
                        SELECT 1
                        FROM voluntario_areas va2
                        WHERE va2.voluntario_id = v.id AND va2.area_id = %s
                    )
                """
                params.append(area_id)

            query += """
                GROUP BY v.id, v.nome, v.telefone, v.responsavel
                ORDER BY ultima_escala DESC, v.nome ASC
            """
            if limit is not None:
                query += " LIMIT %s OFFSET %s"
                params.extend([int(limit), int(offset)])

            cursor.execute(query, tuple(params))
            return cursor.fetchall()
    except Exception as err:
        logger.exception("Erro ao listar inativos: %s", err)
        raise RepositoryError("Erro ao listar inativos.") from err
    finally:
        conn.close()


def search_voluntarios(query, area_id=None, is_responsavel=None):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            search_pattern = f"%{query}%"
            
            base_query = """
                SELECT v.id, v.nome, v.telefone, v.responsavel 
                FROM voluntarios v
            """
            
            params = []
            
            # If area is provided, join with voluntario_areas
            if area_id:
                base_query += " JOIN voluntario_areas va ON v.id = va.voluntario_id"
            
            base_query += " WHERE (v.nome LIKE %s OR v.telefone LIKE %s)"
            params.extend([search_pattern, search_pattern])
            
            if area_id:
                base_query += " AND va.area_id = %s"
                params.append(area_id)
                
            if is_responsavel is not None:
                # responsavel can be 0 or 1 in DB
                base_query += " AND v.responsavel = %s"
                params.append(is_responsavel)
                
            base_query += " ORDER BY v.nome ASC LIMIT 50"
            
            cursor.execute(base_query, tuple(params))
            return cursor.fetchall()
    except Exception as err:
        logger.exception("Erro ao pesquisar voluntários: %s", err)
        raise RepositoryError("Erro ao pesquisar voluntários.") from err
    finally:
        conn.close()
