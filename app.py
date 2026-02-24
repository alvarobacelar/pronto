from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db_connection, init_db
import os
from datetime import datetime, timedelta
import calendar

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_secreta_padrao_admin')

# User admin password (in a real app this should be hashed in DB, for simplicity we use an env var)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Inicializar o banco de dados
init_db()

# --- Funções Utilitárias ---
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

@app.template_filter('data_br')
def format_data_br(data_iso):
    if not data_iso or len(data_iso) != 10:
        return data_iso
    partes = data_iso.split('-')
    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return data_iso

def check_auth():
    return session.get('admin_logged_in') is True

# --- Rotas Públicas ---

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM areas')
    areas = cursor.fetchall()
    cursor.close()
    conn.close()
    
    hoje = datetime.now()
    prox_mes = hoje.month + 1 if hoje.month < 12 else 1
    prox_ano = hoje.year if hoje.month < 12 else hoje.year + 1
    domingos = get_domingos_mes(prox_ano, prox_mes)
    
    return render_template('index.html', areas=areas, domingos=domingos)

@app.route('/agendar', methods=['POST'])
def agendar():
    telefone = request.form.get('telefone')
    area_id = request.form.get('area_id')
    data = request.form.get('data')
    turno = request.form.get('turno')
    
    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)
    
    # 1. Validar se o voluntário existe
    #voluntario = cursor.execute('SELECT * FROM voluntarios WHERE telefone = %s', (telefone,)).fetchone()
    cursor.execute('SELECT * FROM voluntarios WHERE telefone = %s', (telefone,))
    voluntario = cursor.fetchone()

    if not voluntario:
        conn.close()
        return jsonify({"status": "error", "message": "Voluntário não cadastrado no sistema."}), 400
        
    # 1.5 Validar se pertence à área
    cursor.execute('SELECT 1 FROM voluntario_areas WHERE voluntario_id = %s AND area_id = %s', (voluntario['id'], area_id))
    pertence = cursor.fetchone()
    if not pertence:
        conn.close()
        return jsonify({"status": "error", "message": "Você não está habilitado(a) para servir nesta área."}), 400
        
    # 2. Validar limite de vagas
    cursor.execute('SELECT * FROM areas WHERE id = %s', (area_id,))
    area = cursor.fetchone()
    if not area:
        conn.close()
        return jsonify({"status": "error", "message": "Área inválida."}), 400
        
    max_pessoas = area['max_pessoas']
    
    cursor.execute('''
        SELECT count(e.id) as count FROM escalas e
        JOIN voluntarios v ON e.voluntario_id = v.id
        WHERE e.area_id = %s AND e.data = %s AND e.turno = %s AND (v.responsavel = 0 OR v.responsavel IS NULL)
    ''', (area_id, data, turno))
    agendados = cursor.fetchone()['count']
    
    if agendados >= max_pessoas:
        conn.close()
        return jsonify({"status": "error", "message": "Vagas esgotadas para esta área/turno."}), 400
        
    # 3. Validar se já está agendado para o mesmo turno e data
    cursor.execute('''
        SELECT id FROM escalas 
        WHERE voluntario_id = %s AND data = %s AND turno = %s
    ''', (voluntario['id'], data, turno))
    ja_agendado = cursor.fetchone()
    
    if ja_agendado:
         conn.close()
         return jsonify({"status": "error", "message": "Você já está escalado(a) neste dia e turno."}), 400
    
    # 4. Inserir Escala
    cursor.execute('''
        INSERT INTO escalas (voluntario_id, area_id, data, turno)
        VALUES (%s, %s, %s, %s)
    ''', (voluntario['id'], area_id, data, turno))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "message": "Escala confirmada com sucesso!"})

@app.route('/api/voluntario/areas', methods=['GET'])
def get_voluntario_areas():
    telefone = request.args.get('telefone')
    if not telefone:
        return jsonify({"status": "error", "message": "Telefone não informado."}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT id, nome FROM voluntarios WHERE telefone = %s', (telefone,))
    voluntario = cursor.fetchone()
    
    if not voluntario:
        conn.close()
        return jsonify({"status": "error", "message": "Voluntário não cadastrado."}), 404
        
    cursor.execute('''
        SELECT a.id, a.nome 
        FROM areas a
        JOIN voluntario_areas va ON a.id = va.area_id
        WHERE va.voluntario_id = %s
    ''', (voluntario['id'],))
    areas = cursor.fetchall()
    
    conn.close()
    
    areas_list = [{"id": a['id'], "nome": a['nome']} for a in areas]
    return jsonify({
        "status": "success", 
        "nome": voluntario['nome'],
        "areas": areas_list
    })

@app.route('/api/vagas', methods=['GET'])
def check_vagas():
    area_id = request.args.get('area_id')
    data = request.args.get('data')
    turno = request.args.get('turno')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT max_pessoas FROM areas WHERE id = %s', (area_id,))
    area = cursor.fetchone()
    if not area:
        conn.close()
        return jsonify({"vagas_disponiveis": 0, "lotado": True})
        
    cursor.execute('''
        SELECT count(e.id) as count FROM escalas e
        JOIN voluntarios v ON e.voluntario_id = v.id
        WHERE e.area_id = %s AND e.data = %s AND e.turno = %s AND (v.responsavel = 0 OR v.responsavel IS NULL)
    ''', (area_id, data, turno))
    agendados = cursor.fetchone()['count']
    conn.close()
    
    vagas_livres = area['max_pessoas'] - agendados
    return jsonify({
        "vagas_disponiveis": max(0, vagas_livres),
        "lotado": vagas_livres <= 0
    })

@app.route('/api/resumo_vagas', methods=['GET'])
def resumo_vagas():
    area_id = request.args.get('area_id')
    if not area_id:
        return jsonify({"error": "Missing area_id"})
        
    hoje = datetime.now()
    prox_mes = hoje.month + 1 if hoje.month < 12 else 1
    prox_ano = hoje.year if hoje.month < 12 else hoje.year + 1
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT max_pessoas FROM areas WHERE id = %s', (area_id,))
    area = cursor.fetchone()
    if not area:
        cursor.close()
        conn.close()
        app.logger.error("Area not found")
        return jsonify({"error": "Area not found"})
        
    max_p = area['max_pessoas']
    
    query = '''
        SELECT e.data, e.turno, count(e.id) as total
        FROM escalas e
        JOIN voluntarios v ON e.voluntario_id = v.id
        WHERE e.area_id = %s AND e.data LIKE %s AND (v.responsavel = 0 OR v.responsavel IS NULL)
        GROUP BY e.data, e.turno
    '''
    query_responsavel = '''
        SELECT e.data, e.turno, count(e.id) as total
        FROM escalas e
        JOIN voluntarios v ON e.voluntario_id = v.id
        WHERE e.area_id = %s AND e.data LIKE %s AND v.responsavel = 1
        GROUP BY e.data, e.turno
    '''
    
    params = (area_id, f"{prox_ano}-{prox_mes:02d}-%")
    
    cursor.execute(query, params)
    agrupado = cursor.fetchall()
    
    cursor.execute(query_responsavel, params)
    agrupado_responsavel = cursor.fetchall()
    
    resultado = {}
    for r in agrupado:
        d = r['data'].strftime('%Y-%m-%d') if hasattr(r['data'], 'strftime') else str(r['data'])
        t = r['turno']
        resultado.setdefault(d, {})[t] = r['total']

    resultado_responsavel = {}
    for r in agrupado_responsavel:
        d = r['data'].strftime('%Y-%m-%d') if hasattr(r['data'], 'strftime') else str(r['data'])
        t = r['turno']
        resultado_responsavel.setdefault(d, {})[t] = r['total']
        
    domingos = get_domingos_mes(prox_ano, prox_mes)
    resumo_final = []

    app.logger.info(f"Dicionário Resultado: {resultado}")
    
    for dom in domingos:
        d_iso = dom['iso']
        d_br = dom['br'][:5]
        
        manha_esc = resultado.get(d_iso, {}).get("Manhã", 0)
        noite_esc = resultado.get(d_iso, {}).get("Noite", 0)
        manha_esc_resp = resultado_responsavel.get(d_iso, {}).get("Manhã", 0)
        noite_esc_resp = resultado_responsavel.get(d_iso, {}).get("Noite", 0)
        
        resumo_final.append({
            "iso": d_iso,
            "br": d_br,
            "manha_escalados": manha_esc,
            "manha_responsavel": manha_esc_resp,
            "noite_escalados": noite_esc,
            "noite_responsavel": noite_esc_resp,
            "manha_livres": max(0, max_p - manha_esc),
            "noite_livres": max(0, max_p - noite_esc)
        })
    
    cursor.close()
    conn.close()
    return jsonify({"max_pessoas": max_p, "domingos": resumo_final})

# --- Rotas Administrativas ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        senha = request.form.get('senha')
        if senha == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Senha incorreta', 'danger')
            
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if not check_auth():
        return redirect(url_for('admin_login'))
        
    area_filter = request.args.get('area_id')
    month_year = request.args.get('month_year')
    
    hoje = datetime.now()
    if month_year:
        try:
            ano, mes = map(int, month_year.split('-'))
        except:
            ano, mes = hoje.year, hoje.month
    else:
        ano, mes = hoje.year, hoje.month
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Busca áreas
    cursor.execute('SELECT * FROM areas')
    areas = cursor.fetchall()
    
    if not area_filter and areas:
        area_filter = str(areas[0]['id'])
    
    domingos = get_domingos_mes(ano, mes)
    
    query = '''
        SELECT e.id, v.nome as voluntario_nome, v.responsavel, e.area_id, a.nome as area_nome, e.data, e.turno
        FROM escalas e
        JOIN voluntarios v ON e.voluntario_id = v.id
        JOIN areas a ON e.area_id = a.id
        WHERE e.data LIKE %s
    '''
    params = [f"{ano}-{mes:02d}-%"]
    
    if area_filter:
        query += ' AND e.area_id = %s'
        params.append(area_filter)
        
    query += ' ORDER BY a.nome ASC, e.data ASC, e.turno ASC, v.responsavel DESC, v.nome ASC'
    
    cursor.execute(query, params)
    escalas = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    grids = {}
    for a in areas:
        if area_filter and str(a['id']) != str(area_filter):
            continue
        grids[a['nome']] = {d['iso']: {"Manhã": {"responsavel": [], "equipe": []}, "Noite": {"responsavel": [], "equipe": []}} for d in domingos}
        
    for e in escalas:
        area_n = e['area_nome']
        d_iso = e['data']
        d_iso_str = d_iso.strftime('%Y-%m-%d') if hasattr(d_iso, 'strftime') else d_iso
        
        turno = e['turno']
        is_resp = e['responsavel']
        if area_n in grids and d_iso_str in grids[area_n]:
            if is_resp:
                grids[area_n][d_iso_str][turno]["responsavel"].append({"id": e['id'], "nome": e['voluntario_nome']})
            else:
                grids[area_n][d_iso_str][turno]["equipe"].append({"id": e['id'], "nome": e['voluntario_nome']})
            
    max_rows = {}
    for area_n, dias in grids.items():
        m_len = 0
        for d_iso, turnos in dias.items():
            m_len = max(m_len, len(turnos["Manhã"]["equipe"]), len(turnos["Noite"]["equipe"]))
        max_rows[area_n] = max(m_len + 1, 2)
        
    meses_nomes = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    mes_str = f"{meses_nomes[mes]} / {ano}"
    
    lista_meses = []
    curr_dt = datetime(hoje.year, hoje.month, 1)
    for _ in range(2):
        if curr_dt.month == 1:
            curr_dt = datetime(curr_dt.year - 1, 12, 1)
        else:
            curr_dt = datetime(curr_dt.year, curr_dt.month - 1, 1)
            
    curr_m, curr_y = curr_dt.month, curr_dt.year
    for i in range(12):
        lista_meses.append({"val": f"{curr_y}-{curr_m:02d}", "nome": f"{meses_nomes[curr_m].capitalize()} {curr_y}"})
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1
            
    my_sel = f"{ano}-{mes:02d}"
            
    return render_template('admin/dashboard.html', 
                            areas=areas, 
                            grids=grids, 
                            domingos=domingos, 
                            mes_str=mes_str, 
                            max_rows=max_rows,
                            lista_meses=lista_meses,
                            my_sel=my_sel,
                            area_sel=area_filter)
@app.route('/admin/voluntarios', methods=['GET', 'POST'])
def admin_voluntarios():
    if not check_auth(): return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        nome = request.form.get('nome')
        telefone = request.form.get('telefone')
        responsavel = 1 if request.form.get('responsavel') == 'on' else 0
        areas_selecionadas = request.form.getlist('areas')
        
        try:
            cursor.execute('INSERT INTO voluntarios (nome, telefone, responsavel) VALUES (%s, %s, %s)', (nome, telefone, responsavel))
            voluntario_id = cursor.lastrowid
            
            for area_id in areas_selecionadas:
                cursor.execute('INSERT INTO voluntario_areas (voluntario_id, area_id) VALUES (%s, %s)', (voluntario_id, int(area_id)))
                
            conn.commit()
            flash('Voluntário cadastrado.', 'success')
        except sqlite3.IntegrityError:
             flash('Telefone já cadastrado.', 'danger')
             
    query = '''
        SELECT v.*, GROUP_CONCAT(a.nome, ', ') as areas_nomes
        FROM voluntarios v
        LEFT JOIN voluntario_areas va ON v.id = va.voluntario_id
        LEFT JOIN areas a ON va.area_id = a.id
        GROUP BY v.id
        ORDER BY v.responsavel DESC, v.nome ASC
    '''
    cursor.execute(query)
    voluntarios = cursor.fetchall()
    cursor.execute('SELECT * FROM areas ORDER BY nome ASC')
    areas = cursor.fetchall()
    conn.close()
    return render_template('admin/voluntarios.html', voluntarios=voluntarios, areas=areas)

@app.route('/admin/voluntarios/<int:id>/delete', methods=['POST'])
def delete_voluntario(id):
    if not check_auth(): return redirect(url_for('admin_login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('DELETE FROM escalas WHERE voluntario_id = %s', (id,))
    cursor.execute('DELETE FROM voluntario_areas WHERE voluntario_id = %s', (id,))
    cursor.execute('DELETE FROM voluntarios WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    flash('Voluntário removido.', 'success')
    return redirect(url_for('admin_voluntarios'))
    
@app.route('/admin/voluntarios/<int:id>/edit', methods=['GET', 'POST'])
def edit_voluntario(id):
    if not check_auth(): return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM voluntarios WHERE id = %s', (id,))
    voluntario = cursor.fetchone()
    
    if not voluntario:
        conn.close()
        flash('Voluntário não encontrado.', 'danger')
        return redirect(url_for('admin_voluntarios'))
        
    if request.method == 'POST':
        nome = request.form.get('nome')
        telefone = request.form.get('telefone')
        responsavel = 1 if request.form.get('responsavel') == 'on' else 0
        areas_selecionadas = request.form.getlist('areas')
        
        try:
            cursor.execute('UPDATE voluntarios SET nome = %s, telefone = %s, responsavel = %s WHERE id = %s', (nome, telefone, responsavel, id))
            cursor.execute('DELETE FROM voluntario_areas WHERE voluntario_id = %s', (id,))
            
            for area_id in areas_selecionadas:
                cursor.execute('INSERT INTO voluntario_areas (voluntario_id, area_id) VALUES (%s, %s)', (id, int(area_id)))
                
            conn.commit()
            flash('Voluntário atualizado.', 'success')
            conn.close()
            return redirect(url_for('admin_voluntarios'))
        except sqlite3.IntegrityError:
            flash('Telefone já cadastrado por outro voluntário.', 'danger')
            
    # GET: Buscar áreas do voluntário
    cursor.execute('SELECT area_id FROM voluntario_areas WHERE voluntario_id = %s', (id,))
    va = cursor.fetchall()
    voluntario_areas_ids = [r['area_id'] for r in va]
    
    cursor.execute('SELECT * FROM areas ORDER BY nome ASC')
    areas = cursor.fetchall()
    conn.close()
    
    return render_template('admin/voluntario_edit.html', voluntario=voluntario, voluntario_areas_ids=voluntario_areas_ids, areas=areas)
    
@app.route('/admin/inativos', methods=['GET'])
def admin_inativos():
    if not check_auth(): return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    hoje = datetime.now()
    # Pega aproximadamente os 60 dias passados como limite de tolerância
    limite = hoje - timedelta(days=60)
    data_limite_iso = limite.strftime('%Y-%m-%d')
    
    # Busca voluntários que não possuem NENHUMA escala com data >= data_limite_iso
    query = '''
        SELECT v.id, v.nome, v.telefone, v.responsavel,
               (SELECT MAX(e.data) FROM escalas e WHERE e.voluntario_id = v.id) as ultima_escala
        FROM voluntarios v
        WHERE v.id NOT IN (
            SELECT DISTINCT voluntario_id 
            FROM escalas 
            WHERE data >= %s
        )
        ORDER BY ultima_escala DESC, v.nome ASC
    '''
    cursor.execute(query, (data_limite_iso,))
    inativos = cursor.fetchall()
    conn.close()
    
    return render_template('admin/inativos.html', inativos=inativos, data_limite=limite)

@app.route('/admin/areas', methods=['GET', 'POST'])
def admin_areas():
    if not check_auth(): return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        nome = request.form.get('nome')
        max_pessoas = request.form.get('max_pessoas')
        cursor.execute('INSERT INTO areas (nome, max_pessoas) VALUES (%s, %s)', (nome, int(max_pessoas)))
        conn.commit()
        flash('Área cadastrada.', 'success')
        
    cursor.execute('SELECT * FROM areas')
    areas = cursor.fetchall()
    conn.close()
    return render_template('admin/areas.html', areas=areas)
    
@app.route('/admin/areas/<int:id>/delete', methods=['POST'])
def delete_area(id):
    if not check_auth(): return redirect(url_for('admin_login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('DELETE FROM escalas WHERE area_id = %s', (id,))
    cursor.execute('DELETE FROM voluntario_areas WHERE area_id = %s', (id,))
    cursor.execute('DELETE FROM areas WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    flash('Área removida.', 'success')
    return redirect(url_for('admin_areas'))

@app.route('/admin/escalas/<int:id>/delete', methods=['POST'])
def delete_escala(id):
    if not check_auth(): return redirect(url_for('admin_login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('DELETE FROM escalas WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    flash('Agendamento cancelado.', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)