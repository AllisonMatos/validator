# 🛡️ Leak Validator (Cognitive Credential Auditor)

**Leak Validator** é uma solução avançada de automação para segurança ofensiva, projetada para processar, normalizar e validar credenciais vazadas (leaks) em larga escala. Diferente de validadores tradicionais baseados em seletores estáticos, esta ferramenta utiliza um **Agente Validador Cognitivo** que interpreta a interface do usuário para interagir de forma humana e resiliente.

---

## 🚀 Funcionalidades Principais

### 1. Normalização Híbrida Inteligente
Processa arquivos brutos de leaks e combo lists bagunçadas.
*   **Regex Engine**: Extrai padrões `url:user:pass` de arquivos desestruturados.
*   **Lógica de Memória**: Agrupa automaticamente usuários por domínio, otimizando o processo de validação.

### 2. Agente Validador Cognitivo
A verdadeira inteligência por trás da ferramenta.
*   **Visão Semântica**: O robô não depende de IDs ou seletores CSS fixos. Ele "lê" o texto dos botões ("Entrar", "Login", "Próximo") e identifica campos de entrada dinamicamente.
*   **Simulação Humana**: Movimentos e intervalos que mimetizam o comportamento de um usuário real, dificultando a detecção por sistemas anti-bot básicos.

### 3. Navegação Adaptável
*   **Persistence Mode**: Abre uma janela única do Chromium para facilitar o monitoramento visual.
*   **Headless Mode**: Execução silenciosa em segundo plano para máxima performance.
*   **Auto-Correction**: Sistema de redirecionamento inteligente (`redirection_rules.json`) para corrigir URLs migradas ou quebradas.

---

## 🛠 Instalação

### Pré-requisitos
*   Python 3.8+
*   Pip (gerenciador de pacotes)

### Passo a Passo (Automático)
Basta rodar o script de setup para configurar o ambiente virtual e as dependências:
```bash
chmod +x setup.sh
./setup.sh
```

### Passo a Passo (Manual)
Se preferir configurar manualmente:
```bash
# Criar e ativar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependências Python
pip install -r requirements.txt

# Instalar o motor do navegador (Playwright)
playwright install chromium
playwright install-deps chromium
```

---

## 📖 Como Usar

### Passo 1: Normalização (Limpeza de Dados)
Transforme seu arquivo `.txt` bruto em um formato que o validador entenda.
```bash
./run_normalization.sh seu_arquivo_de_leak.txt
```
*   **Resultado**: Arquivos JSON e CSV limpos na pasta `outputs/`.

### Passo 2: Validação (O Robô em Ação)
Execute o validador apontando para o JSON gerado.

**Modo Monitorado (Janela Visível):**
```bash
./run_validator.sh outputs/seu_arquivo_processado.json
```

**Modo "Silent" (Invisível + Screenshots de Evidência):**
```bash
./run_validator.sh outputs/seu_arquivo_processado.json --headless --screenshot-all
```

---

## 📂 Compreendendo a Saída (`outputs/`)

Após a execução, a ferramenta organiza os resultados para facilitar sua análise:

*   ✅ `*_valid.txt`: Credenciais confirmadas ou que requerem ação adicional (como MFA/Token).
*   ❌ `*_invalid.txt`: Falhas de login, senhas incorretas ou sites inacessíveis.
*   📸 `screenshots/`: (Se ativado) Prints de cada tentativa, servindo como prova visual do sucesso ou falha.

---

## 🧠 Como Funciona o "Cérebro"?

O validador utiliza uma camada de abstração sobre o navegador. Quando encontra uma página de login:
1.  **Analisa** todos os elementos interativos.
2.  **Classifica** os campos (usuário, senha, botão de submissão) baseando-se em atributos semânticos e texto visível.
3.  **Executa** a sequência de login, lidando com transições de página e carregamentos dinâmicos.
4.  **Avalia** a resposta do site (mudança de URL, mensagens de erro, presença de dashboards) para determinar o status da credencial.

---

## ⚠️ Aviso Legal
*Esta ferramenta foi desenvolvida exclusivamente para fins educacionais e testes de segurança autorizados. O uso em sistemas sem permissão explícita é ilegal.*
