#!/bin/sh
set -e

cd /app

echo "Aguardando banco de dados..."
until dart run bin/wait_for_db.dart; do
  echo "Banco indisponível, tentando novamente em 2s..."
  sleep 2
done

echo "Inicializando schema e seed..."
dart run bin/seed.dart

echo "Iniciando servidor na porta 8080..."
exec dart build/bin/server.dart
