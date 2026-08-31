#!/bin/sh
set -e

echo "Aguardando PostgreSQL..."
python -c "
import time, os, sys
import psycopg2
host = os.environ.get('DB_HOST', 'app2-db')
port = int(os.environ.get('DB_PORT', '5432'))
user = os.environ['DB_USER']
password = os.environ['DB_PASSWORD']
dbname = os.environ['DB_NAME']
for i in range(60):
    try:
        conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
        conn.close()
        print('PostgreSQL pronto.')
        sys.exit(0)
    except psycopg2.OperationalError:
        time.sleep(1)
print('Timeout aguardando PostgreSQL', file=sys.stderr)
sys.exit(1)
"

echo "Aplicando migracoes..."
alembic upgrade head

echo "Iniciando aplicacao..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
