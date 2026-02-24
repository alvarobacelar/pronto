import mysql.connector
from mysql.connector import pooling
import os
import logging

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações do Banco de Dados extraídas das variáveis de ambiente do Docker
DB_CONFIG = {
    "host": os.environ.get('DB_HOST', '127.0.0.1'),
    "user": os.environ.get('DB_USER', 'root'),
    "password": os.environ.get('DB_PASSWORD', 'password'),
    "database": os.environ.get('DB_NAME', 'escala'),
    "charset": 'utf8mb4',
    "collation": 'utf8mb4_general_ci',
    "auth_plugin": 'caching_sha2_password'
}

# Inicialização do Pool de Conexões
try:
    # O pool ajuda a gerir múltiplas conexões sem travar o MySQL
    db_pool = pooling.MySQLConnectionPool(
        pool_name="pronto_pool",
        pool_size=5, # Máximo de 5 conexões simultâneas por worker do Gunicorn
        pool_reset_session=True,
        **DB_CONFIG
    )
    logger.info("MySQL Connection Pool criado com sucesso.")
except mysql.connector.Error as err:
    logger.error(f"Erro ao criar o pool: {err}")
    # Se o banco não estiver pronto (ex: no boot do docker), o sistema avisará
    db_pool = None

def get_db_connection():
    """
    Obtém uma conexão do pool. 
    Lembre-se de sempre usar conn.close() no app.py para devolver a conexão ao pool.
    """
    try:
        if db_pool:
            return db_pool.get_connection()
        else:
            # Fallback direto caso o pool não tenha sido iniciado
            return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        logger.error(f"Erro ao obter conexão: {err}")
        return None

def init_db():
    """
    Cria a estrutura de tabelas necessária para o sistema Pronto.
    Ajustado para sintaxe MySQL (Auto Increment e Motores InnoDB).
    """
    conn = get_db_connection()
    if not conn:
        logger.error("Não foi possível conectar ao banco para inicialização.")
        return

    cursor = conn.cursor()
    
    try:
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

        conn.commit()
        logger.info("Estrutura do banco de dados verificada/criada com sucesso.")
    except mysql.connector.Error as err:
        logger.error(f"Erro na criação das tabelas: {err}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    init_db()