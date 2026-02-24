# Estágio 1: Build
FROM python:3.11-slim AS builder

WORKDIR /app

# Evita que o Python gere arquivos .pyc e permite logs em tempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instala dependências de compilação
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Estágio 2: Runtime
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SECRET_KEY=8f9e2d7c1a5b4d3e0f9c8b7a6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e \
    ADMIN_PASSWORD=admin123 \
    DB_HOST=172.17.0.2 \
    DB_USER=root \
    DB_PASSWORD=password \
    DB_NAME=escala \
    BD_DATABASE=escala

# Copia apenas as dependências instaladas do estágio de build
COPY --from=builder /install /usr/local
COPY . .

# Cria um usuário não-root para segurança
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Porta padrão do Flask
EXPOSE 5001

# Comando para rodar a aplicação usando Gunicorn (recomendado para produção)
# Substitua 'app:app' pelo seu arquivo:variável_flask (ex: main:app)
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:5001", "app:app"]