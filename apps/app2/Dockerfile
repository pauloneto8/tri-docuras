FROM python:3.12-slim

WORKDIR /app

# postgresql-client (17 no Debian trixie) lê dumps -Fc atuais; o servidor é 16.
# A restauração reseta o schema public e ignora SET transaction_timeout incompatível.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc tzdata postgresql-client \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Recife

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh \
    && mkdir -p /app/data/backups \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
