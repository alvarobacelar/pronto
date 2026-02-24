import pymysql
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.environ.get('DB_HOST', '127.0.0.1'),
    "user": os.environ.get('DB_USER', 'root'),
    "password": os.environ.get('DB_PASSWORD', 'password'),
    "database": os.environ.get('DB_NAME', 'escala'),
    "charset": 'utf8mb4',
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": True,
    "ssl": {}, 
    "client_flag": pymysql.constants.CLIENT.PLUGIN_AUTH
}

def get_db_connection():
    """
    Obtém uma conexão usando PyMySQL.
    Esta biblioteca resolve o erro de 'Plugin mysql_native_password not loaded'
    pois implementa o protocolo de autenticação nativamente em Python.
    """
    try:
        conn = pymysql.connect(**DB_CONFIG)
        return conn
    except Exception as err:
        logger.error(f"Erro ao obter conexão com MySQL: {err}")
        return None

def init_db():
    """
    Cria a estrutura de tabelas necessária para o sistema Pronto.
    """
    conn = get_db_connection()
    if not conn:
        logger.error("Não foi possível conectar ao banco para inicialização.")
        return

    try:
        # No PyMySQL o uso do 'with' garante o fechamento do cursor
        with conn.cursor() as cursor:
            # Tabela de Áreas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS areas (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nome VARCHAR(100) NOT NULL,
                    max_pessoas INT DEFAULT 2
                ) ENGINE=InnoDB;
            ''')

            # Tabela de Voluntários
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS voluntarios (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nome VARCHAR(100) NOT NULL,
                    telefone VARCHAR(20) UNIQUE NOT NULL,
                    responsavel TINYINT(1) DEFAULT 0
                ) ENGINE=InnoDB;
            ''')

            # Tabela de Escalas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS escalas (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    voluntario_id INT,
                    area_id INT,
                    data DATE,
                    turno VARCHAR(20),
                    FOREIGN KEY (voluntario_id) REFERENCES voluntarios(id) ON DELETE CASCADE,
                    FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE CASCADE
                ) ENGINE=InnoDB;
            ''')

            # Tabela de Relacionamento Voluntário x Áreas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS voluntario_areas (
                    voluntario_id INT,
                    area_id INT,
                    PRIMARY KEY (voluntario_id, area_id),
                    FOREIGN KEY (voluntario_id) REFERENCES voluntarios(id) ON DELETE CASCADE,
                    FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE CASCADE
                ) ENGINE=InnoDB;
            ''')

        logger.info("Estrutura do banco de dados verificada/criada com sucesso.")
    except Exception as err:
        logger.error(f"Erro na criação das tabelas: {err}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()