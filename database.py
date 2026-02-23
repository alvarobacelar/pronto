import sqlite3
import os

DATABASE_URL = "escala.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabela de áreas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            max_pessoas INTEGER NOT NULL
        )
    ''')
    
    # Tabela de voluntários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voluntarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL UNIQUE,
            responsavel BOOLEAN DEFAULT 0
        )
    ''')
    
    # Tabela de escalas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS escalas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voluntario_id INTEGER NOT NULL,
            area_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            turno TEXT NOT NULL,
            FOREIGN KEY (voluntario_id) REFERENCES voluntarios (id),
            FOREIGN KEY (area_id) REFERENCES areas (id)
        )
    ''')
    # Tabela de relação voluntário-área
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voluntario_areas (
            voluntario_id INTEGER NOT NULL,
            area_id INTEGER NOT NULL,
            PRIMARY KEY (voluntario_id, area_id),
            FOREIGN KEY (voluntario_id) REFERENCES voluntarios (id) ON DELETE CASCADE,
            FOREIGN KEY (area_id) REFERENCES areas (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Banco de dados inicializado com sucesso.")
