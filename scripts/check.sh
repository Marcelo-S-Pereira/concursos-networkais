#!/usr/bin/env bash
# Verificação local. Substitui a CI enquanto não existe repositório remoto
# (ver planos/plano_v4_1_ajustes_e_rota_ate_sabado.md, §1.6).
set -euo pipefail
raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "── backend: lint ──"
"$raiz/backend/.venv/bin/ruff" check "$raiz/backend/app" "$raiz/backend/tests"

echo "── backend: testes ──"
(cd "$raiz/backend" && ./.venv/bin/pytest -q)

echo "── frontend: typecheck + build ──"
(cd "$raiz/frontend" && npm run build --silent)

echo "── segredos: nada de .env rastreado ──"
if git -C "$raiz" ls-files --error-unmatch .env >/dev/null 2>&1; then
    echo "FALHOU: .env está rastreado pelo git"; exit 1
fi
echo "tudo certo."
