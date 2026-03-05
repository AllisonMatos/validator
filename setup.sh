#!/bin/bash
# Setup completo para o Leak Validator
set -e

echo "🔧 Configurando ambiente..."

# 1. Criar venv se não existir
if [ ! -d "venv" ]; then
    echo "📦 Criando ambiente virtual..."
    python3 -m venv venv
fi

# 2. Ativar venv
source venv/bin/activate

# 3. Instalar dependências Python
echo "📥 Instalando dependências Python..."
pip install -r requirements.txt

# 4. Instalar browsers do Playwright
echo "🌐 Instalando browsers do Playwright..."
playwright install chromium
playwright install-deps chromium 2>/dev/null || echo "⚠️  install-deps falhou (pode precisar de sudo). Se der erro ao rodar, execute: sudo playwright install-deps"

echo ""
echo "✅ Setup completo! Agora pode rodar:"
echo "   ./run_normalization.sh SEU_ARQUIVO.txt"
echo "   ./run_validator.sh outputs/SEU_ARQUIVO.json"
