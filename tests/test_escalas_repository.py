import pytest
from unittest.mock import MagicMock, patch
from repositories.escalas_repository import (
    create_escala, 
    delete_escala, 
    escala_exists, 
    get_dashboard_data, 
    count_agendados_non_responsavel,
    get_resumo_vagas
)
from repositories.errors import RepositoryError
from datetime import date

@pytest.fixture
def mock_db_conn():
    with patch("repositories.escalas_repository.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        yield mock_conn

def test_escala_exists(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = {"id": 1}
    
    exists = escala_exists(1, "2024-05-19", "Manhã")
    
    assert exists is True
    mock_cursor.execute.assert_called_once()

def test_create_escala(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    
    create_escala(1, 2, "2024-05-19", "Noite")
    
    mock_cursor.execute.assert_called_once()
    mock_db_conn.commit.assert_called_once()

def test_count_agendados_non_responsavel(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = {"count": 5}
    count = count_agendados_non_responsavel(1, "2024-05-19", "Manhã")
    assert count == 5
    mock_cursor.execute.assert_called_once()

def test_delete_escala(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    delete_escala(1)
    mock_cursor.execute.assert_called_once()
    mock_db_conn.commit.assert_called_once()

def test_get_resumo_vagas(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    # 1. Area found
    mock_cursor.fetchone.return_value = {"max_pessoas": 10}
    mock_cursor.fetchall.side_effect = [[{"data": date(2024, 5, 19), "turno": "Manhã", "total": 2}], []]
    
    max_p, agr, agr_resp = get_resumo_vagas(1, 2024, 5)
    assert max_p == 10
    assert len(agr) == 1
    assert len(agr_resp) == 0

def test_get_resumo_vagas_not_found(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = None
    max_p, agr, agr_resp = get_resumo_vagas(999, 2024, 5)
    assert max_p is None

def test_get_dashboard_data(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.side_effect = [[{"id": 1, "nome": "Som"}], [{"id": 10, "voluntario_nome": "João"}]]
    areas, escalas = get_dashboard_data(2024, 5)
    assert len(areas) == 1
    assert len(escalas) == 1

def test_repository_error_handling(mock_db_conn):
    from repositories.errors import RepositoryError
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.execute.side_effect = Exception("DB Error")
    
    with pytest.raises(RepositoryError):
        count_agendados_non_responsavel(1, "2024-05-19", "Manhã")
    
    with pytest.raises(RepositoryError):
        get_resumo_vagas(1, 2024, 5)
    
    with pytest.raises(RepositoryError):
        delete_escala(1)

def test_get_dashboard_data_filtered(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.side_effect = [[], []]
    areas, escalas = get_dashboard_data(2024, 5, area_filter="1")
    assert mock_cursor.execute.call_count == 2
    args, kwargs = mock_cursor.execute.call_args
    assert "area_id = %s" in args[0]

def test_escalas_errors_extra(mock_db_conn):
    from repositories.errors import RepositoryError
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.execute.side_effect = Exception("DB Error")
    
    with pytest.raises(RepositoryError):
        get_dashboard_data(2024, 5)
    
    with pytest.raises(RepositoryError):
        escala_exists(1, "2024-05-19", "Manhã")

def test_create_escala_error(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.execute.side_effect = Exception("Insert Error")
    with pytest.raises(RepositoryError):
        create_escala(1, 1, "2024-05-19", "Manhã")
