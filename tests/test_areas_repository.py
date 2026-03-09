import pytest
from unittest.mock import MagicMock, patch
from repositories.areas_repository import list_areas, get_area_by_id, create_area, update_area, delete_area
from repositories.errors import RepositoryError

@pytest.fixture
def mock_db_conn():
    with patch("repositories.areas_repository.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        yield mock_conn

def test_list_areas(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.return_value = [{"id": 1, "nome": "Som", "max_pessoas": 2}]
    
    areas = list_areas()
    
    assert len(areas) == 1
    assert areas[0]["nome"] == "Som"
    mock_cursor.execute.assert_called_once_with("SELECT * FROM areas")

def test_get_area_by_id(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = {"id": 1, "nome": "Som", "max_pessoas": 2}
    
    area = get_area_by_id(1)
    
    assert area["id"] == 1
    assert area["nome"] == "Som"
    mock_cursor.execute.assert_called_once_with("SELECT * FROM areas WHERE id = %s", (1,))

def test_create_area(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    
    create_area("Mídia", 3, "0_Manhã,0_Noite,4_Noite")
    
    mock_cursor.execute.assert_called_once()
    mock_db_conn.commit.assert_called_once()

def test_update_area(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    
    update_area(1, "Som Editado", 4, "0_Manhã,0_Noite,4_Noite")
    
    mock_cursor.execute.assert_called_once()
    mock_db_conn.commit.assert_called_once()

def test_delete_area(mock_db_conn):
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    
    delete_area(1)
    
    assert mock_cursor.execute.call_count == 3
    mock_db_conn.commit.assert_called_once()

def test_list_areas_error(mock_db_conn):
    mock_db_conn.cursor.side_effect = Exception("DB Error")
    
    with pytest.raises(RepositoryError):
        list_areas()
