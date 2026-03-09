import pytest
from unittest.mock import MagicMock, patch
from repositories.voluntarios_repository import (
    create_voluntario, 
    delete_voluntario, 
    get_voluntario_by_id, 
    get_voluntario_by_phone,
    list_voluntarios_with_areas,
    update_voluntario,
    voluntario_has_area,
    list_inativos,
    count_inativos,
    get_voluntario_with_areas_by_phone,
    get_voluntario_area_ids
)
from repositories.errors import RepositoryError, DuplicatePhoneError

@pytest.fixture
def mock_db_conn():
    with patch("repositories.voluntarios_repository.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        yield mock_conn

def test_get_voluntario_by_phone(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = {"id": 1, "nome": "João", "telefone": "123456789"}
    
    v = get_voluntario_by_phone("123456789")
    
    assert v["nome"] == "João"
    mock_cursor.execute.assert_called_once()

def test_create_voluntario(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.lastrowid = 1
    
    create_voluntario("Maria", "987654321", 0, ["1", "2"])
    
    # One for voluntarios table, two for voluntario_areas relations
    assert mock_cursor.execute.call_count == 3
    mock_db_conn.commit.assert_called_once()

def test_create_voluntario_duplicate_phone(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    import pymysql
    mock_cursor.execute.side_effect = pymysql.IntegrityError(1062, "Duplicate entry '123' for key 'telefone'")
    with pytest.raises(DuplicatePhoneError):
        create_voluntario("Maria", "123", 0, [])

def test_get_voluntario_by_id(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = {"id": 1, "nome": "João"}
    v = get_voluntario_by_id(1)
    assert v["nome"] == "João"

def test_voluntario_has_area(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = {"1": 1}
    assert voluntario_has_area(1, 1) is True

def test_list_voluntarios_with_areas(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.side_effect = [[{"id": 1, "nome": "João"}], [{"id": 1, "nome": "Som"}]]
    mock_cursor.fetchone.return_value = {"total": 1}
    voluntarios, areas, total_count = list_voluntarios_with_areas()
    assert len(voluntarios) == 1
    assert len(areas) == 1

def test_delete_voluntario(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    delete_voluntario(1)
    assert mock_cursor.execute.call_count == 3
    mock_db_conn.commit.assert_called_once()

def test_update_voluntario(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    update_voluntario(1, "João Mod", "123", 1, ["1"])
    assert mock_cursor.execute.call_count == 3
    mock_db_conn.commit.assert_called_once()

def test_list_inativos(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.return_value = [{"id": 1, "nome": "Inativo"}]
    inativos = list_inativos("2024-05-19")
    assert len(inativos) == 1

def test_list_inativos_with_filters(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.return_value = []
    list_inativos("2024-05-19", nome_filter="Jo", area_id=2, limit=30, offset=60)
    query, params = mock_cursor.execute.call_args[0]
    assert "v.nome LIKE %s" in query
    assert "EXISTS" in query
    assert "LIMIT %s OFFSET %s" in query
    assert params == ("2024-05-19", "%Jo%", 2, 30, 60)

def test_count_inativos_with_filters(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = {"total": 42}
    total = count_inativos("2024-05-19", nome_filter="Jo", area_id=2)
    query, params = mock_cursor.execute.call_args[0]
    assert "COUNT(*) as total" in query
    assert "v.nome LIKE %s" in query
    assert "EXISTS" in query
    assert params == ("2024-05-19", "%Jo%", 2)
    assert total == 42

def test_voluntarios_repository_errors(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.execute.side_effect = Exception("Error")
    
    with pytest.raises(RepositoryError):
        get_voluntario_by_id(1)
    
    with pytest.raises(RepositoryError):
        get_voluntario_by_phone("123")
        
    with pytest.raises(RepositoryError):
        voluntario_has_area(1, 1)

    with pytest.raises(RepositoryError):
        list_voluntarios_with_areas()
    
    with pytest.raises(RepositoryError):
        delete_voluntario(1)

def test_get_voluntario_with_areas_by_phone(mock_db_conn):
    from repositories.voluntarios_repository import get_voluntario_with_areas_by_phone
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    # 1. Voluntário encontrado
    mock_cursor.fetchone.return_value = {"id": 1, "nome": "João"}
    mock_cursor.fetchall.return_value = [{"id": 1, "nome": "Som"}]
    v, areas = get_voluntario_with_areas_by_phone("123")
    assert v["id"] == 1
    assert len(areas) == 1
    
    # 2. Voluntário não encontrado
    mock_cursor.fetchone.return_value = None
    v, areas = get_voluntario_with_areas_by_phone("999")
    assert v is None
    assert areas == []

def test_get_voluntario_area_ids(mock_db_conn):
    from repositories.voluntarios_repository import get_voluntario_area_ids
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.return_value = [{"area_id": 1}, {"area_id": 2}]
    ids = get_voluntario_area_ids(1)
    assert ids == [1, 2]

def test_voluntarios_repository_errors_extended(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.execute.side_effect = Exception("General Error")
    
    with pytest.raises(RepositoryError):
        get_voluntario_with_areas_by_phone("123")
    with pytest.raises(RepositoryError):
        get_voluntario_area_ids(1)
    with pytest.raises(RepositoryError):
        update_voluntario(1, "N", "T", 0, [])
    with pytest.raises(RepositoryError):
        list_inativos("2024-01-01")
    with pytest.raises(RepositoryError):
        count_inativos("2024-01-01")
    with pytest.raises(RepositoryError):
        create_voluntario("N", "T", 0, [])

def test_update_voluntario_duplicate(mock_db_conn):
    from repositories.voluntarios_repository import update_voluntario
    from repositories.errors import DuplicatePhoneError
    import pymysql
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.execute.side_effect = pymysql.IntegrityError(1062, "Duplicate")
    with pytest.raises(DuplicatePhoneError):
        update_voluntario(1, "N", "T", 0, [])
