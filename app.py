from datetime import datetime, timedelta
import calendar
import os
import re

import pandas as pd

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from database import init_db
from repositories.areas_repository import (
    create_area,
    delete_area as repo_delete_area,
    get_area_by_id,
    list_areas,
    update_area,
)
from repositories.errors import DuplicatePhoneError, RepositoryError
from repositories.escalas_repository import (
    count_agendados_non_responsavel,
    create_escala,
    delete_escala as repo_delete_escala,
    escala_exists,
    get_dashboard_data,
    get_resumo_vagas,
)
from repositories.voluntarios_repository import (
    count_inativos,
    create_voluntario,
    delete_voluntario as repo_delete_voluntario,
    get_voluntario_area_ids,
    get_voluntario_by_id,
    get_voluntario_by_phone,
    get_voluntario_with_areas_by_phone,
    list_inativos,
    list_voluntarios_with_areas,
    update_voluntario,
    voluntario_has_area,
    search_voluntarios,
    get_voluntarios_nao_escalados,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave_secreta_padrao_admin")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

init_db()


def get_domingos_mes(ano, mes):
    cal = calendar.monthcalendar(ano, mes)
    domingos = []
    for semana in cal:
        if semana[calendar.SUNDAY] != 0:
            dia = semana[calendar.SUNDAY]
            data_iso = f"{ano}-{mes:02d}-{dia:02d}"
            data_br = f"{dia:02d}/{mes:02d}/{ano}"
            domingos.append({"iso": data_iso, "br": data_br})
    return domingos


def get_dates_for_area(area_config, ano, mes):
    """
    Returns a list of dates and shifts available for a given area config.
    area_config is a string like "0_Manhã,0_Noite,3_Noite"
    """
    if not area_config:
        return []

    config_parts = area_config.split(",")
    # map day_idx -> list of shifts
    allowed = {}
    for part in config_parts:
        if "_" in part:
            d_idx, shift = part.split("_")
            allowed.setdefault(int(d_idx), []).append(shift)

    cal = calendar.monthcalendar(ano, mes)
    dates = []
    
    # calendar.monthcalendar: 0 is Monday, 6 is Sunday
    # Our UI: 0 is Sunday, 1 is Monday ... 6 is Saturday
    # Python's weekday(): 0 is Monday, 6 is Sunday
    
    for week in cal:
        for day_idx_in_week, day in enumerate(week):
            if day == 0:
                continue
            
            # Convert day_idx_in_week (0=Mon, 6=Sun) to our UI idx (0=Sun, 1=Mon, ..., 6=Sat)
            ui_idx = (day_idx_in_week + 1) % 7
            
            if ui_idx in allowed:
                data_iso = f"{ano}-{mes:02d}-{day:02d}"
                data_br = f"{day:02d}/{mes:02d}/{ano}"
                dates.append({
                    "iso": data_iso, 
                    "br": data_br, 
                    "turnos": allowed[ui_idx]
                })
    return sorted(dates, key=lambda x: x["iso"])


@app.template_filter("data_br")
def format_data_br(data_iso):
    if not data_iso or len(data_iso) != 10:
        return data_iso
    partes = data_iso.split("-")
    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return data_iso


def check_auth():
    return session.get("admin_logged_in") is True


@app.route("/")
def index():
    try:
        areas = list_areas()
    except RepositoryError:
        return "Erro ao conectar ao banco de dados.", 503

    hoje = datetime.now()
    prox_mes = hoje.month + 1 if hoje.month < 12 else 1
    prox_ano = hoje.year if hoje.month < 12 else hoje.year + 1
    domingos = get_domingos_mes(prox_ano, prox_mes)

    return render_template("index.html", areas=areas, domingos=domingos)


@app.route("/agendar", methods=["POST"])
def agendar():
    telefone = request.form.get("telefone")
    area_id = request.form.get("area_id")
    slots = request.form.getlist("slots")  # format: "YYYY-MM-DD|Turno"

    if not slots:
        # Fallback for old single selection if still sent
        data = request.form.get("data")
        turno = request.form.get("turno")
        if data and turno:
            slots = [f"{data}|{turno}"]

    if not slots:
        return jsonify({"status": "error", "message": "Nenhum horário selecionado."}), 400

    try:
        voluntario = get_voluntario_by_phone(telefone)
        if not voluntario:
            return jsonify({"status": "error", "message": "Voluntário não cadastrado no sistema."}), 400

        if not voluntario_has_area(voluntario["id"], area_id):
            return jsonify({"status": "error", "message": "Você não está habilitado(a) para servir nesta área."}), 400

        area = get_area_by_id(area_id)
        if not area:
            return jsonify({"status": "error", "message": "Área inválida."}), 400

        sucessos = 0
        erros = []

        for slot in slots:
            try:
                data_val, turno_val = slot.split("|")
            except ValueError:
                erros.append(f"Formato de horário inválido: {slot}")
                continue

            agendados = count_agendados_non_responsavel(area_id, data_val, turno_val)
            if agendados >= area["max_pessoas"]:
                erros.append(f"Vagas esgotadas para {data_val} ({turno_val}).")
                continue

            if escala_exists(voluntario["id"], data_val, turno_val):
                erros.append(f"Você já está escalado(a) em {data_val} ({turno_val}).")
                continue

            create_escala(voluntario["id"], area_id, data_val, turno_val)
            sucessos += 1

        if sucessos > 0:
            msg = f"{sucessos} agendamento(s) realizado(s) com sucesso!"
            if erros:
                msg += " Alguns horários não puderam ser marcados: " + "; ".join(erros)
            return jsonify({"status": "success", "message": msg})
        else:
            return jsonify({"status": "error", "message": "Não foi possível realizar nenhum agendamento: " + "; ".join(erros)}), 400

    except RepositoryError:
        return jsonify({"status": "error", "message": "Erro interno ao processar agendamento."}), 500


@app.route("/api/voluntario/areas", methods=["GET"])
def get_voluntario_areas():
    telefone = request.args.get("telefone")
    if not telefone:
        return jsonify({"status": "sucesso", "message": "area cadastrada."}), 400

    try:
        voluntario, areas = get_voluntario_with_areas_by_phone(telefone)
    except RepositoryError:
        return jsonify({"status": "error", "message": "Erro interno ao consultar voluntário."}), 500

    if not voluntario:
        return jsonify({"status": "error", "message": "Voluntário não cadastrado."}), 404

    return jsonify({"status": "success", "nome": voluntario["nome"], "areas": areas})


@app.route("/api/vagas", methods=["GET"])
def check_vagas():
    area_id = request.args.get("area_id")
    data = request.args.get("data")
    turno = request.args.get("turno")

    try:
        area = get_area_by_id(area_id)
        if not area:
            return jsonify({"vagas_disponiveis": 0, "lotado": True})

        agendados = count_agendados_non_responsavel(area_id, data, turno)
        vagas_livres = area["max_pessoas"] - agendados

        return jsonify({"vagas_disponiveis": max(0, vagas_livres), "lotado": vagas_livres <= 0})
    except RepositoryError:
        return jsonify({"vagas_disponiveis": 0, "lotado": True}), 500


@app.route("/api/resumo_vagas", methods=["GET"])
def resumo_vagas():
    area_id = request.args.get("area_id")
    if not area_id:
        return jsonify({"area": "Area cadastrada"})

    hoje = datetime.now()
    prox_mes = hoje.month + 1 if hoje.month < 12 else 1
    prox_ano = hoje.year if hoje.month < 12 else hoje.year + 1

    try:
        max_p, agrupado, agrupado_responsavel = get_resumo_vagas(area_id, prox_ano, prox_mes)
    except RepositoryError:
        return jsonify({"error": "Erro ao gerar resumo"}), 500

    if max_p is None:
        app.logger.error("Area not found")
        return jsonify({"error": "Area not found"})

    resultado = {}
    for r in agrupado:
        d = r["data"].strftime("%Y-%m-%d") if hasattr(r["data"], "strftime") else str(r["data"])
        t = r["turno"]
        resultado.setdefault(d, {})[t] = r["total"]

    resultado_responsavel = {}
    for r in agrupado_responsavel:
        d = r["data"].strftime("%Y-%m-%d") if hasattr(r["data"], "strftime") else str(r["data"])
        t = r["turno"]
        resultado_responsavel.setdefault(d, {})[t] = r["total"]

    area = get_area_by_id(area_id)
    if not area:
        return jsonify({"error": "Area not found"}), 404

    availability = area.get("dias_disponiveis", "0_Manhã,0_Noite") # Default to Sundays if empty
    dates_config = get_dates_for_area(availability, prox_ano, prox_mes)
    
    resumo_final = []

    for item in dates_config:
        d_iso = item["iso"]
        d_br = item["br"][:5]
        turnos_permitidos = item["turnos"]

        dias = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']

        # --- Lógica para o dia da semana ---
        data_obj = datetime.strptime(d_iso, "%Y-%m-%d")
        dia_semana = dias[data_obj.weekday()] # Pega "Segunda" de "Segunda-feira"
        # -----------------------------------

        res_item = {
            "iso": d_iso,
            "br": d_br,
            "dia_semana": dia_semana,
            "turnos": []
        }

        for t in ["Manhã", "Noite"]:
            if t in turnos_permitidos:
                esc = resultado.get(d_iso, {}).get(t, 0)
                resp = resultado_responsavel.get(d_iso, {}).get(t, 0)
                res_item["turnos"].append({
                    "nome": t,
                    "escalados": esc,
                    "responsavel": resp,
                    "vagas_livres": max(0, max_p - esc)
                })
        
        resumo_final.append(res_item)

    return jsonify({"max_pessoas": max_p, "datas": resumo_final})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        senha = request.form.get("senha")
        if senha == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Senha incorreta", "danger")

    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("index"))


def _build_dashboard_context(is_admin):
    """Build the template context for the dashboard / escala page."""
    area_filter = request.args.get("area_id")
    month_year = request.args.get("month_year")

    hoje = datetime.now()
    if month_year:
        try:
            ano, mes = map(int, month_year.split("-"))
        except Exception:
            ano, mes = hoje.year, hoje.month
    else:
        ano, mes = hoje.year, hoje.month

    try:
        areas, escalas = get_dashboard_data(ano, mes, area_filter)
    except RepositoryError:
        flash("Erro ao carregar dashboard.", "danger")
        return render_template(
            "admin/dashboard.html", areas=[], grids={}, domingos=[], mes_str="",
            max_rows={}, lista_meses=[], my_sel="", area_sel=None, is_admin=is_admin,
            nao_escalados=[],
        )

    if not area_filter and areas:
        area_filter = str(areas[0]["id"])

    nao_escalados = []
    if is_admin and area_filter:
        try:
            nao_escalados = get_voluntarios_nao_escalados(ano, mes, int(area_filter))
        except RepositoryError:
            pass

    # Get unique dates for the grid based on the area's availability
    area_objs = {str(a["id"]): a for a in areas}
    
    # If a filter is selected, we only show that area's dates. 
    # If no filter (showing all), we might still want to show all days that have assignments or Sundays as default.
    grid_dates = []
    if area_filter and area_filter in area_objs:
        target_area = area_objs[area_filter]
        availability = target_area.get("dias_disponiveis", "0_Manhã,0_Noite")
        grid_dates = get_dates_for_area(availability, ano, mes)
    else:
        # Default fallback to Sundays if no area filter or multi-area view
        grid_dates = get_domingos_mes(ano, mes)

    # Ensure dates from existing escalas are also included if they fall outside standard config (safety)
    existing_iso_dates = set(d["iso"] for d in grid_dates)
    for escala in escalas:
        d_escala = escala["data"]
        d_iso = d_escala.strftime("%Y-%m-%d") if hasattr(d_escala, "strftime") else str(d_escala)
        if d_iso not in existing_iso_dates:
            # We don't have the BR format easily here without a helper, but let's try to keeping it consistent
            d_dt = datetime.strptime(d_iso, "%Y-%m-%d")
            existing_iso_dates.add(d_iso)
            grid_dates.append({"iso": d_iso, "br": d_dt.strftime("%d/%m/%Y")})
    
    grid_dates = sorted(grid_dates, key=lambda x: x["iso"])

    grids = {}
    for area in areas:
        if area_filter and str(area["id"]) != str(area_filter):
            continue
        grids[area["nome"]] = {
            "id": area["id"],
            "dias": {
                dia["iso"]: {"Manhã": {"responsavel": [], "equipe": []}, "Noite": {"responsavel": [], "equipe": []}}
                for dia in grid_dates
            }
        }

    for escala in escalas:
        area_nome = escala["area_nome"]
        data_escala = escala["data"]
        data_iso = data_escala.strftime("%Y-%m-%d") if hasattr(data_escala, "strftime") else data_escala
        turno = escala["turno"]
        if area_nome in grids and data_iso in grids[area_nome]["dias"]:
            grupo = "responsavel" if escala["responsavel"] else "equipe"
            grids[area_nome]["dias"][data_iso][turno][grupo].append({"id": escala["id"], "nome": escala["voluntario_nome"]})

    max_rows = {}
    for area_nome, dados in grids.items():
        maior = 0
        for turnos in dados["dias"].values():
            maior = max(maior, len(turnos["Manhã"]["equipe"]), len(turnos["Noite"]["equipe"]))
        max_rows[area_nome] = max(maior + 2, 2)

    meses_nomes = [
        "",
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    mes_str = f"{meses_nomes[mes]} / {ano}"

    lista_meses = []
    curr_dt = datetime(hoje.year, hoje.month, 1)
    for _ in range(2):
        if curr_dt.month == 1:
            curr_dt = datetime(curr_dt.year - 1, 12, 1)
        else:
            curr_dt = datetime(curr_dt.year, curr_dt.month - 1, 1)

    curr_m, curr_y = curr_dt.month, curr_dt.year
    for _ in range(12):
        lista_meses.append({"val": f"{curr_y}-{curr_m:02d}", "nome": f"{meses_nomes[curr_m].capitalize()} {curr_y}"})
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1

    my_sel = f"{ano}-{mes:02d}"

    return render_template(
        "admin/dashboard.html",
        areas=areas,
        grids=grids,
        domingos=grid_dates, # renamed to match template expectation but contains flex dates
        mes_str=mes_str,
        max_rows=max_rows,
        lista_meses=lista_meses,
        my_sel=my_sel,
        area_sel=area_filter,
        is_admin=is_admin,
        nao_escalados=nao_escalados,
    )


# @app.route("/escala")
# def escala_publica():
#     return _build_dashboard_context(is_admin=False)


@app.route("/admin")
def admin_dashboard():
    if not check_auth():
        return redirect(url_for("admin_login"))

    return _build_dashboard_context(is_admin=True)


@app.route("/admin/voluntarios", methods=["GET", "POST"])
def admin_voluntarios():
    if not check_auth():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        responsavel = 1 if request.form.get("responsavel") == "on" else 0
        areas_selecionadas = request.form.getlist("areas")

        try:
            create_voluntario(nome, telefone, responsavel, areas_selecionadas)
            flash("Voluntário cadastrado.", "success")
        except DuplicatePhoneError:
            flash("Telefone já cadastrado.", "danger")
        except RepositoryError:
            flash("Erro ao cadastrar voluntário.", "danger")

    try:
        area_filter = request.args.get("area_id")
        search_query = request.args.get("q", "").strip()
        try:
            page = int(request.args.get("page", 1))
            if page < 1:
                page = 1
        except ValueError:
            page = 1
            
        limit = 30
        offset = (page - 1) * limit
        
        voluntarios, areas, total_count = list_voluntarios_with_areas(area_filter, search_query, limit, offset)
        
        import math
        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
        
    except RepositoryError:
        flash("Erro ao carregar voluntários.", "danger")
        voluntarios, areas, total_count = [], [], 0
        search_query = ""
        page = 1
        total_pages = 1

    return render_template(
        "admin/voluntarios.html", 
        voluntarios=voluntarios, 
        areas=areas, 
        area_filter=area_filter,
        search_query=search_query,
        page=page,
        total_pages=total_pages,
        total_count=total_count
    )


@app.route("/admin/voluntarios/import", methods=["POST"])
def admin_voluntarios_import():
    if not check_auth():
        return redirect(url_for("admin_login"))

    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Nenhum arquivo selecionado.", "danger")
        return redirect(url_for("admin_voluntarios"))

    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(file)
            # Support for Brazilian Excel CSVs separated by ';'
            if len(df.columns) == 1 and ';' in str(df.columns[0]):
                file.seek(0)
                df = pd.read_csv(file, sep=';')
        elif file.filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file)
        else:
            flash("Formato de arquivo não suportado. Use CSV ou Excel.", "danger")
            return redirect(url_for("admin_voluntarios"))

        # Normalize column names to lowercase and strip whitespaces
        df.columns = df.columns.astype(str).str.strip().str.lower()

        # Check required columns
        app.logger.info(df.columns)
        if "nome" not in df.columns or "telefone" not in df.columns:
            flash("O arquivo deve conter pelo menos as colunas 'Nome' e 'Telefone'.", "danger")
            return redirect(url_for("admin_voluntarios"))

        # Fetch areas map
        try:
            areas_db = list_areas()
            # Map lowercase area name to area id
            areas_map = {str(a["nome"]).lower().strip(): a["id"] for a in areas_db}
        except RepositoryError:
            areas_map = {}

        importados = 0
        existentes = 0
        erros = 0

        for index, row in df.iterrows():
            nome_val = row.get("nome")
            # Skip if nome is NaN
            if pd.isna(nome_val):
                continue
                
            nome = str(nome_val).strip()
            telefone_bruto = str(row.get("telefone", ""))
            
            # Avoid nan string if imported empty cells
            if telefone_bruto.lower() == 'nan':
                telefone_bruto = ""
                
            telefone = re.sub(r'\D', '', telefone_bruto)

            if not nome or not telefone:
                erros += 1
                continue

            # Check if phone exists
            try:
                existente = get_voluntario_by_phone(telefone)
                if existente:
                    existentes += 1
                    continue
            except RepositoryError:
                erros += 1
                continue

            # Parse 'responsavel' / 'lider'
            responsavel = 0
            for col in ["lider", "líder", "responsável", "responsavel"]:
                if col in df.columns:
                    val = str(row.get(col, "")).strip().lower()
                    if val in ["sim", "s", "true", "1"]:
                        responsavel = 1
                    break

            # Parse 'areas'
            areas_selecionadas = []
            for col in ["area", "área", "areas", "áreas"]:
                if col in df.columns:
                    area_val = str(row.get(col, ""))
                    if area_val and area_val.lower() != 'nan':
                        # Split by comma or semicolon
                        nomes_areas = [a.strip().lower() for a in re.split(r'[,;]', area_val) if a.strip()]
                        for nome_area in nomes_areas:
                            if nome_area in areas_map:
                                areas_selecionadas.append(str(areas_map[nome_area]))
                    break

            try:
                create_voluntario(nome, telefone, responsavel, areas_selecionadas)
                importados += 1
            except (DuplicatePhoneError, RepositoryError):
                erros += 1

        flash(f"Importação concluída: {importados} importados, {existentes} já existiam, {erros} com erro.", "success")

    except Exception as e:
        app.logger.exception("Erro na importação: %s", e)
        flash(f"Erro ao processar o arquivo: {str(e)}", "danger")

    return redirect(url_for("admin_voluntarios"))


@app.route("/admin/voluntarios/<int:id>/delete", methods=["POST"])
def delete_voluntario(id):
    if not check_auth():
        return redirect(url_for("admin_login"))

    try:
        repo_delete_voluntario(id)
        flash("Voluntário removido.", "success")
    except RepositoryError:
        flash("Erro ao remover voluntário.", "danger")
    return redirect(url_for("admin_voluntarios"))


@app.route("/admin/voluntarios/<int:id>/edit", methods=["GET", "POST"])
def edit_voluntario(id):
    if not check_auth():
        return redirect(url_for("admin_login"))

    try:
        voluntario = get_voluntario_by_id(id)
    except RepositoryError:
        flash("Erro ao carregar voluntário.", "danger")
        return redirect(url_for("admin_voluntarios"))

    if not voluntario:
        flash("Voluntário não encontrado.", "danger")
        return redirect(url_for("admin_voluntarios"))

    if request.method == "POST":
        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        responsavel = 1 if request.form.get("responsavel") == "on" else 0
        areas_selecionadas = request.form.getlist("areas")

        try:
            update_voluntario(id, nome, telefone, responsavel, areas_selecionadas)
            flash("Voluntário atualizado.", "success")
            return redirect(url_for("admin_voluntarios"))
        except DuplicatePhoneError:
            flash("Telefone já cadastrado por outro voluntário.", "danger")
        except RepositoryError:
            flash("Erro ao atualizar voluntário.", "danger")

    try:
        voluntario_areas_ids = get_voluntario_area_ids(id)
        areas = list_areas()
    except RepositoryError:
        flash("Erro ao carregar áreas.", "danger")
        voluntario_areas_ids, areas = [], []

    return render_template(
        "admin/voluntario_edit.html",
        voluntario=voluntario,
        voluntario_areas_ids=voluntario_areas_ids,
        areas=areas,
    )


@app.route("/admin/inativos", methods=["GET"])
def admin_inativos():
    if not check_auth():
        return redirect(url_for("admin_login"))

    limite = datetime.now() - timedelta(days=60)
    data_limite_iso = limite.strftime("%Y-%m-%d")
    nome_filter = request.args.get("nome", "").strip()
    area_filter_raw = request.args.get("area_id", "").strip()
    area_filter = int(area_filter_raw) if area_filter_raw.isdigit() else None
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 30
    offset = (page - 1) * per_page

    try:
        total_count = count_inativos(data_limite_iso, nome_filter=nome_filter, area_id=area_filter)
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        if page > total_pages:
            page = total_pages
            offset = (page - 1) * per_page

        inativos = list_inativos(
            data_limite_iso,
            nome_filter=nome_filter,
            area_id=area_filter,
            limit=per_page,
            offset=offset,
        )
    except RepositoryError:
        flash("Erro ao carregar inativos.", "danger")
        inativos = []
        total_count = 0
        total_pages = 1

    try:
        areas = list_areas()
    except RepositoryError:
        flash("Erro ao carregar áreas.", "danger")
        areas = []

    return render_template(
        "admin/inativos.html",
        inativos=inativos,
        data_limite=limite,
        areas=areas,
        nome_filter=nome_filter,
        area_filter=area_filter,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
    )


@app.route("/admin/areas", methods=["GET", "POST"])
def admin_areas():
    if not check_auth():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        nome = request.form.get("nome")
        max_pessoas = request.form.get("max_pessoas")
        disponibilidade = ",".join(request.form.getlist("disponibilidade"))
        try:
            create_area(nome, max_pessoas, disponibilidade)
            flash("Área cadastrada.", "success")
        except RepositoryError:
            flash("Erro ao cadastrar área.", "danger")

    try:
        areas = list_areas()
    except RepositoryError:
        flash("Erro ao carregar áreas.", "danger")
        areas = []

    return render_template("admin/areas.html", areas=areas)


@app.route("/admin/areas/<int:id>/delete", methods=["POST"])
def delete_area(id):
    if not check_auth():
        return redirect(url_for("admin_login"))

    try:
        repo_delete_area(id)
        flash("Área removida.", "success")
    except RepositoryError:
        flash("Erro ao remover área.", "danger")
    return redirect(url_for("admin_areas"))


@app.route("/admin/areas/<int:id>/edit", methods=["GET", "POST"])
def edit_area(id):
    if not check_auth():
        return redirect(url_for("admin_login"))

    try:
        area = get_area_by_id(id)
    except RepositoryError:
        flash("Erro ao carregar área.", "danger")
        return redirect(url_for("admin_areas"))

    if not area:
        flash("Área não encontrada.", "danger")
        return redirect(url_for("admin_areas"))

    if request.method == "POST":
        nome = request.form.get("nome")
        max_pessoas = request.form.get("max_pessoas")
        disponibilidade = ",".join(request.form.getlist("disponibilidade"))
        try:
            update_area(id, nome, max_pessoas, disponibilidade)
            flash("Área atualizada.", "success")
            return redirect(url_for("admin_areas"))
        except RepositoryError:
            flash("Erro ao atualizar área.", "danger")

    return render_template("admin/area_edit.html", area=area)


@app.route("/admin/escalas/<int:id>/delete", methods=["POST"])
def delete_escala(id):
    if not check_auth():
        return redirect(url_for("admin_login"))

    try:
        repo_delete_escala(id)
        flash("Agendamento cancelado.", "success")
    except RepositoryError:
        flash("Erro ao cancelar agendamento.", "danger")
    return redirect(request.referrer or url_for("admin_dashboard"))


@app.route("/admin/api/voluntarios/search", methods=["GET"])
def api_admin_voluntarios_search():
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401

    query = request.args.get("q", "").strip()
    area_id = request.args.get("area_id")
    is_responsavel = request.args.get("is_responsavel")
    
    if is_responsavel is not None and is_responsavel != "":
        is_responsavel = int(is_responsavel)
    else:
        is_responsavel = None

    if not query or len(query) < 2:
        return jsonify([])

    try:
        resultados = search_voluntarios(query, area_id, is_responsavel)
        return jsonify(resultados)
    except RepositoryError:
        return jsonify({"error": "Erro ao buscar voluntários"}), 500


@app.route("/admin/escala/add", methods=["POST"])
def admin_escala_add():
    if not check_auth():
        return redirect(url_for("admin_login"))

    voluntario_id = request.form.get("voluntario_id")
    area_id = request.form.get("area_id")
    data = request.form.get("data")
    turno = request.form.get("turno")

    if not all([voluntario_id, area_id, data, turno]):
        flash("Todos os campos do modal (voluntário, área, data, turno) são obrigatórios.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        # Admin bypasses some validations, but we shouldn't allow duplicates on the same day/shift
        if escala_exists(voluntario_id, data, turno):
            flash("O voluntário selecionado já está escalado neste dia e turno.", "warning")
        else:
            create_escala(voluntario_id, area_id, data, turno)
            flash("Voluntário adicionado à escala.", "success")
            
            # Helper to redirect to the updated view
            if data and len(data) >= 7:
                month_year = data[:7]  # YYYY-MM
                return redirect(url_for("admin_dashboard", month_year=month_year, area_id=area_id))

    except RepositoryError:
        flash("Erro ao salvar agendamento no banco de dados.", "danger")

    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5001))
    app.run(host=host, port=port, debug=True)
