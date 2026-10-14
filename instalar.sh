#!/usr/bin/env bash
# Instalação na VPS (Ubuntu/Debian). Rode de dentro da pasta do projeto:
#   bash instalar.sh
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "🐳 Instalando o Docker (script oficial get.docker.com)..."
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "❌ O Docker está instalado, mas falta o 'docker compose' (plugin v2)."
  echo "   Siga: https://docs.docker.com/compose/install/linux/"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "🐍 Instalando o Python 3 (usado só pelo configurador)..."
  apt-get update -qq && apt-get install -y -qq python3
fi

if [ ! -f .env ]; then
  python3 scripts/configurar.py
else
  echo "ℹ️  Já existe um .env. Para refazer as perguntas: python3 scripts/configurar.py"
fi

echo "🚀 Subindo os serviços..."
docker compose up -d --build

echo
echo "Pronto! Próximos passos:"
if grep -q '^CANAL=evolution' .env; then
  echo "  docker compose exec agente python -m scripts.conectar_whatsapp"
fi
echo "  docker compose exec agente python -m scripts.simular     (conversa de teste)"
echo "  docker compose exec agente python -m scripts.checar      (diagnóstico)"
