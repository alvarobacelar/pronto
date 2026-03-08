import io
import pytest
from unittest.mock import patch, MagicMock
from flask import session

def test_index_route(client):
    with patch("app.list_areas") as mock_list:
        mock_list.return_value = [{"id": 1, "nome": "Som"}]
        response = client.get("/")
        assert response.status_code == 200
        # Areas are loaded via JS in index.html, so they won't be in the initial HTML
        # Verify static text instead
        assert b"Pronto - Escala de Volunt" in response.data

def test_admin_login_success(client):
    with patch("app.ADMIN_PASSWORD", "testpass"):
        response = client.post("/admin/login", data={"senha": "testpass"}, follow_redirects=True)
        assert response.status_code == 200
        # Check if we are redirected to dashboard or at least session is set
        with client.session_transaction() as sess:
            assert sess.get("admin_logged_in") is True

def test_admin_login_fail(client):
    with patch("app.ADMIN_PASSWORD", "testpass"):
        response = client.post("/admin/login", data={"senha": "wrong"}, follow_redirects=True)
        assert b"Senha incorreta" in response.data
        with client.session_transaction() as sess:
            assert not sess.get("admin_logged_in")

def test_api_vagas(client):
    with patch("app.get_area_by_id") as mock_area, \
         patch("app.count_agendados_non_responsavel") as mock_count:
        
        mock_area.return_value = {"id": 1, "max_pessoas": 10}
        mock_count.return_value = 4
        
        response = client.get("/api/vagas?area_id=1&data=2024-05-19&turno=Manhã")
        data = response.get_json()
        
        assert data["vagas_disponiveis"] == 6
        assert data["lotado"] is False

def test_api_vagas_not_found(client):
    with patch("app.get_area_by_id") as mock_area:
        mock_area.return_value = None
        response = client.get("/api/vagas?area_id=999&data=2024-05-19&turno=Manhã")
        data = response.get_json()
        assert data["vagas_disponiveis"] == 0
        assert data["lotado"] is True

def test_agendar_voluntario_not_found(client):
    with patch("app.get_voluntario_by_phone") as mock_v:
        mock_v.return_value = None
        response = client.post("/agendar", data={
            "telefone": "000", "area_id": "1", "data": "2024-05-19", "turno": "Manhã"
        })
        assert response.status_code == 400
        data = response.get_json()
        assert "Voluntário não cadastrado" in data["message"]

def test_admin_dashboard_unauthorized(client):
    response = client.get("/admin", follow_redirects=True)
    assert b"senha" in response.data.lower()

def test_get_voluntario_areas_success(client):
    with patch("app.get_voluntario_with_areas_by_phone") as mock_get:
        mock_get.return_value = ({"id": 1, "nome": "João"}, [{"id": 1, "nome": "Som"}])
        response = client.get("/api/voluntario/areas?telefone=123")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        assert data["nome"] == "João"
        assert len(data["areas"]) == 1

def test_get_voluntario_areas_not_found(client):
    with patch("app.get_voluntario_with_areas_by_phone") as mock_get:
        mock_get.return_value = (None, [])
        response = client.get("/api/voluntario/areas?telefone=999")
        assert response.status_code == 404
        data = response.get_json()
        assert "não cadastrado" in data["message"]

def test_get_voluntario_areas_missing_phone(client):
    response = client.get("/api/voluntario/areas")
    assert response.status_code == 400
    data = response.get_json()
    assert "não informado" in data["message"]

def test_resumo_vagas_success(client):
    with patch("app.get_resumo_vagas") as mock_resumo, \
         patch("app.get_domingos_mes") as mock_domingos:
        
        mock_resumo.return_value = (10, [{"data": "2024-06-02", "turno": "Manhã", "total": 2}], [])
        mock_domingos.return_value = [{"iso": "2024-06-02", "br": "02/06/2024"}]
        
        response = client.get("/api/resumo_vagas?area_id=1")
        assert response.status_code == 200
        data = response.get_json()
        assert data["max_pessoas"] == 10
        assert len(data["domingos"]) == 1
        assert data["domingos"][0]["manha_escalados"] == 2
        assert data["domingos"][0]["manha_livres"] == 8

def test_resumo_vagas_missing_area_id(client):
    response = client.get("/api/resumo_vagas")
    data = response.get_json()
    assert "Missing area_id" in data["error"]

def test_resumo_vagas_area_not_found(client):
    with patch("app.get_resumo_vagas") as mock_resumo:
        mock_resumo.return_value = (None, [], [])
        response = client.get("/api/resumo_vagas?area_id=999")
        data = response.get_json()
        assert "Area not found" in data["error"]

def test_format_data_br():
    from app import format_data_br
    assert format_data_br("2024-05-19") == "19/05/2024"
    assert format_data_br("invalid") == "invalid"
    assert format_data_br(None) is None
    assert format_data_br("2024-05") == "2024-05"

def test_get_domingos_mes():
    from app import get_domingos_mes
    domingos = get_domingos_mes(2024, 5)
    assert len(domingos) == 4
    assert domingos[0]["iso"] == "2024-05-05"
    assert domingos[3]["iso"] == "2024-05-26"

def test_admin_logout(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.list_areas", return_value=[]):
        response = client.get("/admin/logout", follow_redirects=True)
        assert response.status_code == 200
        with client.session_transaction() as sess:
            assert not sess.get("admin_logged_in")

def test_index_db_error(client):
    from repositories.errors import RepositoryError
    # Use a specific mock to not affect other tests
    with patch("app.list_areas", side_effect=RepositoryError("DB Error")):
        response = client.get("/")
        assert response.status_code == 503
        assert "Erro ao conectar ao banco de dados".encode("utf-8") in response.data

def test_admin_dashboard_logged_in(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.get_dashboard_data") as mock_data:
        mock_data.return_value = ([], [])
        response = client.get("/admin")
        assert response.status_code == 200
        assert "Dashboard".encode("utf-8") in response.data or "Escala".encode("utf-8") in response.data

def test_escala_publica(client):
    with patch("app.get_dashboard_data") as mock_data:
        mock_data.return_value = ([], [])
        response = client.get("/escala")
        assert response.status_code == 200
        assert "Escala".encode("utf-8") in response.data

def test_admin_voluntarios_list(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.list_voluntarios_with_areas") as mock_list:
        mock_list.return_value = ([{"id": 1, "nome": "Vol 1"}], [{"id": 1, "nome": "Area 1"}], 1)
        response = client.get("/admin/voluntarios")
        assert response.status_code == 200
        assert b"Vol 1" in response.data

def test_admin_voluntarios_create(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.create_voluntario") as mock_create, \
         patch("app.list_voluntarios_with_areas") as mock_list:
        mock_list.return_value = ([], [], 0)
        response = client.post("/admin/voluntarios", data={
            "nome": "Novo Vol", "telefone": "123", "areas": ["1", "2"]
        }, follow_redirects=True)
        assert "Voluntário cadastrado".encode("utf-8") in response.data
        mock_create.assert_called_once()

def test_admin_voluntarios_delete(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.repo_delete_voluntario") as mock_delete:
        response = client.post("/admin/voluntarios/1/delete", follow_redirects=True)
        assert "Voluntário removido".encode("utf-8") in response.data
        mock_delete.assert_called_once_with(1)

def test_admin_voluntarios_edit_get(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.get_voluntario_by_id") as mock_get, \
         patch("app.get_voluntario_area_ids") as mock_areas, \
         patch("app.list_areas") as mock_list:
        mock_get.return_value = {"id": 1, "nome": "João", "telefone": "123", "responsavel": 0}
        mock_areas.return_value = [1]
        mock_list.return_value = [{"id": 1, "nome": "Som"}]
        response = client.get("/admin/voluntarios/1/edit")
        assert response.status_code == 200
        assert "Editar Voluntário".encode("utf-8") in response.data

def test_admin_voluntarios_edit_post(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.get_voluntario_by_id", return_value={"id": 1, "nome": "João"}), \
         patch("app.update_voluntario") as mock_update, \
         patch("app.get_voluntario_area_ids", return_value=["1"]), \
         patch("app.list_areas", return_value=[{"id": 1, "nome": "A1"}]), \
         patch("app.list_voluntarios_with_areas", return_value=([], [], 0)):
        response = client.post("/admin/voluntarios/1/edit", data={
            "nome": "Editado", "telefone": "999", "responsavel": "on", "areas": ["1"]
        }, follow_redirects=True)
        assert b"atualizado" in response.data.lower()
        mock_update.assert_called_once()

def test_admin_areas_list(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.list_areas") as mock_list:
        mock_list.return_value = []
        response = client.get("/admin/areas")
        assert response.status_code == 200
        assert "Áreas".encode("utf-8") in response.data

def test_admin_areas_create(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.create_area") as mock_create, \
         patch("app.list_areas") as mock_list:
        mock_list.return_value = []
        response = client.post("/admin/areas", data={"nome": "Nova Area", "max_pessoas": 5}, follow_redirects=True)
        assert "Área cadastrada".encode("utf-8") in response.data
        mock_create.assert_called_once()

def test_admin_areas_edit_get(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.get_area_by_id") as mock_get:
        mock_get.return_value = {"id": 1, "nome": "Som", "max_pessoas": 10}
        response = client.get("/admin/areas/1/edit")
        assert response.status_code == 200
        assert "Editar Área".encode("utf-8") in response.data

def test_admin_areas_edit_post(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.get_area_by_id", return_value={"id": 1, "nome": "Som"}), \
         patch("app.update_area") as mock_update, \
         patch("app.list_areas", return_value=[]):
        response = client.post("/admin/areas/1/edit", data={"nome": "Som Mod", "max_pessoas": 12}, follow_redirects=True)
        assert b"atualizada" in response.data.lower()
        mock_update.assert_called_once()

def test_admin_areas_delete(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.repo_delete_area") as mock_delete, \
         patch("app.list_areas", return_value=[]):
        response = client.post("/admin/areas/1/delete", follow_redirects=True)
        assert "Área removida".encode("utf-8") in response.data
        mock_delete.assert_called_once_with(1)

def test_admin_inativos(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.list_inativos") as mock_list:
        mock_list.return_value = []
        response = client.get("/admin/inativos")
        assert response.status_code == 200
        assert "Inativos".encode("utf-8") in response.data

def test_delete_escala(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.repo_delete_escala") as mock_delete, \
         patch("app.get_dashboard_data", return_value=([], [])):
        response = client.post("/admin/escalas/1/delete", follow_redirects=True)
        assert "Agendamento cancelado".encode("utf-8") in response.data
        mock_delete.assert_called_once_with(1)

def test_admin_dashboard_with_data(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    with patch("app.get_dashboard_data") as mock_data:
        mock_areas = [{"id": 1, "nome": "Som"}]
        mock_escalas = [{
            "id": 10, "area_nome": "Som", "data": "2024-05-19", "turno": "Manhã", 
            "voluntario_nome": "João", "responsavel": 1
        }]
        mock_data.return_value = (mock_areas, mock_escalas)
        response = client.get("/admin?area_id=1&month_year=2024-05")
        assert response.status_code == 200
        assert "Som".encode("utf-8") in response.data
        assert "João".encode("utf-8") in response.data

def test_admin_voluntarios_duplicate_phone(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    from repositories.errors import DuplicatePhoneError
    with patch("app.create_voluntario", side_effect=DuplicatePhoneError()), \
         patch("app.list_voluntarios_with_areas", return_value=([], [], 0)):
        response = client.post("/admin/voluntarios", data={
            "nome": "Novo", "telefone": "123", "areas": ["1"]
        }, follow_redirects=True)
        assert "Telefone já cadastrado".encode("utf-8") in response.data

def test_agendar_not_enabled(client):
    with patch("app.get_voluntario_by_phone") as mock_v, \
         patch("app.voluntario_has_area") as mock_has:
        mock_v.return_value = {"id": 1, "nome": "João"}
        mock_has.return_value = False
        response = client.post("/agendar", data={
            "telefone": "123", "area_id": "1", "data": "2024-05-19", "turno": "Manhã"
        })
        assert response.status_code == 400
        data = response.get_json()
        assert "não está habilitado" in data["message"]

def test_agendar_lotado(client):
    with patch("app.get_voluntario_by_phone", return_value={"id": 1}), \
         patch("app.voluntario_has_area", return_value=True), \
         patch("app.get_area_by_id", return_value={"max_pessoas": 2}), \
         patch("app.count_agendados_non_responsavel", return_value=2):
        response = client.post("/agendar", data={
            "telefone": "123", "area_id": "1", "data": "2024-05-19", "turno": "Manhã"
        })
        assert response.status_code == 400
        data = response.get_json()
        assert "Vagas esgotadas" in data["message"]

def test_agendar_already_scheduled(client):
    with patch("app.get_voluntario_by_phone", return_value={"id": 1}), \
         patch("app.voluntario_has_area", return_value=True), \
         patch("app.get_area_by_id", return_value={"max_pessoas": 5}), \
         patch("app.count_agendados_non_responsavel", return_value=0), \
         patch("app.escala_exists", return_value=True):
        response = client.post("/agendar", data={
            "telefone": "123", "area_id": "1", "data": "2024-05-19", "turno": "Manhã"
        })
        assert response.status_code == 400
        data = response.get_json()
        assert "já está escalado" in data["message"]

def test_admin_voluntarios_import_csv(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    
    csv_content = "Nome,Telefone,Area,Lider\nJoão,11999999999,Som,Sim\nMaria,11888888888,,Não\n"
    data = {
        'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')
    }
    
    with patch("app.list_areas", return_value=[{"id": 1, "nome": "Som"}]), \
         patch("app.get_voluntario_by_phone", side_effect=[None, None]), \
         patch("app.create_voluntario") as mock_create:
        
        response = client.post("/admin/voluntarios/import", data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        assert "2 importados".encode("utf-8") in response.data
        assert mock_create.call_count == 2
        # João
        mock_create.assert_any_call("João", "11999999999", 1, ["1"])
        # Maria
        mock_create.assert_any_call("Maria", "11888888888", 0, [])

def test_admin_voluntarios_import_duplicate(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    
    csv_content = "Nome,Telefone\nPedro,11777777777\n"
    data = {
        'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')
    }
    
    with patch("app.list_areas", return_value=[]), \
         patch("app.get_voluntario_by_phone", return_value={"id": 1, "nome": "Pedro"}), \
         patch("app.create_voluntario") as mock_create:
        
        response = client.post("/admin/voluntarios/import", data=data, content_type='multipart/form-data', follow_redirects=True)
        
        assert response.status_code == 200
        assert "1 já existiam".encode("utf-8") in response.data
        assert mock_create.call_count == 0

def test_admin_voluntarios_import_invalid_file(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    
    data = {
        'file': (io.BytesIO(b"test"), 'test.txt')
    }
    
    response = client.post("/admin/voluntarios/import", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert "Formato de arquivo não suportado".encode("utf-8") in response.data

def test_admin_voluntarios_import_missing_columns(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    
    csv_content = "Idade,Cidade\n20,SP\n"
    data = {
        'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')
    }
    
    response = client.post("/admin/voluntarios/import", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert "O arquivo deve conter".encode("utf-8") in response.data
