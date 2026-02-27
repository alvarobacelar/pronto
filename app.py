from datetime import datetime, timedelta
import calendar
import os

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
    data = request.form.get("data")
    turno = request.form.get("turno")

    try:
        voluntario = get_voluntario_by_phone(telefone)
        if not voluntario:
            return jsonify({"status": "error", "message": "Voluntário não cadastrado no sistema."}), 400

        if not voluntario_has_area(voluntario["id"], area_id):
            return jsonify({"status": "error", "message": "Você não está habilitado(a) para servir nesta área."}), 400

        area = get_area_by_id(area_id)
        if not area:
            return jsonify({"status": "error", "message": "Área inválida."}), 400

        agendados = count_agendados_non_responsavel(area_id, data, turno)
        if agendados >= area["max_pessoas"]:
            return jsonify({"status": "error", "message": "Vagas esgotadas para esta área/turno."}), 400

        if escala_exists(voluntario["id"], data, turno):
            return jsonify({"status": "error", "message": "Você já está escalado(a) neste dia e turno."}), 400

        create_escala(voluntario["id"], area_id, data, turno)
        return jsonify({"status": "success", "message": "Escala confirmada com sucesso!"})
    except RepositoryError:
        return jsonify({"status": "error", "message": "Erro interno ao processar agendamento."}), 500


@app.route("/api/voluntario/areas", methods=["GET"])
def get_voluntario_areas():
    telefone = request.args.get("telefone")
    if not telefone:
        return jsonify({"status": "error", "message": "Telefone não informado."}), 400

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
        return jsonify({"error": "Missing area_id"})

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

    domingos = get_domingos_mes(prox_ano, prox_mes)
    resumo_final = []

    for dom in domingos:
        d_iso = dom["iso"]
        d_br = dom["br"][:5]

        manha_esc = resultado.get(d_iso, {}).get("Manhã", 0)
        noite_esc = resultado.get(d_iso, {}).get("Noite", 0)
        manha_esc_resp = resultado_responsavel.get(d_iso, {}).get("Manhã", 0)
        noite_esc_resp = resultado_responsavel.get(d_iso, {}).get("Noite", 0)

        resumo_final.append(
            {
                "iso": d_iso,
                "br": d_br,
                "manha_escalados": manha_esc,
                "manha_responsavel": manha_esc_resp,
                "noite_escalados": noite_esc,
                "noite_responsavel": noite_esc_resp,
                "manha_livres": max(0, max_p - manha_esc),
                "noite_livres": max(0, max_p - noite_esc),
            }
        )

    return jsonify({"max_pessoas": max_p, "domingos": resumo_final})


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


@app.route("/admin")
def admin_dashboard():
    if not check_auth():
        return redirect(url_for("admin_login"))

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
        return render_template("admin/dashboard.html", areas=[], grids={}, domingos=[], mes_str="", max_rows={}, lista_meses=[], my_sel="", area_sel=None)

    if not area_filter and areas:
        area_filter = str(areas[0]["id"])

    domingos = get_domingos_mes(ano, mes)

    grids = {}
    for area in areas:
        if area_filter and str(area["id"]) != str(area_filter):
            continue
        grids[area["nome"]] = {
            dia["iso"]: {"Manhã": {"responsavel": [], "equipe": []}, "Noite": {"responsavel": [], "equipe": []}}
            for dia in domingos
        }

    for escala in escalas:
        area_nome = escala["area_nome"]
        data_escala = escala["data"]
        data_iso = data_escala.strftime("%Y-%m-%d") if hasattr(data_escala, "strftime") else data_escala
        turno = escala["turno"]
        if area_nome in grids and data_iso in grids[area_nome]:
            grupo = "responsavel" if escala["responsavel"] else "equipe"
            grids[area_nome][data_iso][turno][grupo].append({"id": escala["id"], "nome": escala["voluntario_nome"]})

    max_rows = {}
    for area_nome, dias in grids.items():
        maior = 0
        for turnos in dias.values():
            maior = max(maior, len(turnos["Manhã"]["equipe"]), len(turnos["Noite"]["equipe"]))
        max_rows[area_nome] = max(maior + 1, 2)

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
        domingos=domingos,
        mes_str=mes_str,
        max_rows=max_rows,
        lista_meses=lista_meses,
        my_sel=my_sel,
        area_sel=area_filter,
    )


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
        voluntarios, areas = list_voluntarios_with_areas()
    except RepositoryError:
        flash("Erro ao carregar voluntários.", "danger")
        voluntarios, areas = [], []

    return render_template("admin/voluntarios.html", voluntarios=voluntarios, areas=areas)


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

    try:
        inativos = list_inativos(data_limite_iso)
    except RepositoryError:
        flash("Erro ao carregar inativos.", "danger")
        inativos = []

    return render_template("admin/inativos.html", inativos=inativos, data_limite=limite)


@app.route("/admin/areas", methods=["GET", "POST"])
def admin_areas():
    if not check_auth():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        nome = request.form.get("nome")
        max_pessoas = request.form.get("max_pessoas")
        try:
            create_area(nome, max_pessoas)
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
        try:
            update_area(id, nome, max_pessoas)
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
