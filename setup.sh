#!/usr/bin/env bash
set -e

# ─────────────────────────────────────────────────────────────
# Vocal Analytics Service — Setup Script
# Run once: ./setup.sh
# Then:     python app.py
# ─────────────────────────────────────────────────────────────

REQUIRED_MAJOR=3
REQUIRED_MINOR=11

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "══════════════════════════════════════════════════"
echo "  Vocal Analytics Service — Setup"
echo "══════════════════════════════════════════════════"
echo ""

# ── 1. Check Python version ──────────────────────────────────

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: python3 is not installed.${NC}"
    echo ""
    echo "Please install Python ${REQUIRED_MAJOR}.${REQUIRED_MINOR}+ first:"
    echo "  macOS:  brew install python@3.12"
    echo "  Ubuntu: sudo apt install python3.12 python3.12-venv"
    echo ""
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt "$REQUIRED_MAJOR" ] || { [ "$PY_MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$PY_MINOR" -lt "$REQUIRED_MINOR" ]; }; then
    echo -e "${RED}ERROR: Python ${REQUIRED_MAJOR}.${REQUIRED_MINOR}+ is required, but you have Python ${PY_VERSION}.${NC}"
    echo ""
    echo "Please upgrade Python:"
    echo "  macOS:  brew install python@3.12"
    echo "  Ubuntu: sudo apt install python3.12 python3.12-venv"
    echo ""
    exit 1
fi

echo -e "${GREEN}[OK]${NC} Python ${PY_VERSION} detected"

# ── 2. Check ffmpeg ──────────────────────────────────────────

if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}[WARN]${NC} ffmpeg not found. Audio file transcription will not work."
    echo "       Install it for audio support:"
    echo "         macOS:  brew install ffmpeg"
    echo "         Ubuntu: sudo apt install ffmpeg"
    echo ""
else
    echo -e "${GREEN}[OK]${NC} ffmpeg detected"
fi

# ── 3. Check Ollama (for local LLM mode) ─────────────────────

if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}[INFO]${NC} Ollama not found."
    echo "       Ollama is required only if you want to run LLM locally (LLM_PROVIDER=ollama)."
    echo "       If using OpenAI API instead, you can skip this."
    echo ""
    echo "       To install Ollama for local LLM inference:"
    echo "         macOS:  brew install ollama"
    echo "         Linux:  curl -fsSL https://ollama.com/install.sh | sh"
    echo ""
    echo "       After installing, run:"
    echo "         ollama serve                # Start the Ollama server"
    echo "         ollama pull llama3.1:8b     # Download the model (~4.7 GB)"
    echo ""
else
    echo -e "${GREEN}[OK]${NC} Ollama detected"
    if ollama list 2>/dev/null | grep -q "llama3.1:8b"; then
        echo -e "${GREEN}[OK]${NC} llama3.1:8b model available"
    else
        echo -e "${YELLOW}[INFO]${NC} llama3.1:8b model not pulled yet."
        echo "       Run: ollama pull llama3.1:8b   (if you plan to use LLM_PROVIDER=ollama)"
    fi
fi

# ── 4. Create virtual environment ─────────────────────────────

if [ ! -d ".venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo -e "${GREEN}[OK]${NC} Virtual environment created at .venv/"
else
    echo -e "${GREEN}[OK]${NC} Virtual environment already exists"
fi

# ── 5. Install dependencies ──────────────────────────────────

echo ""
echo "Installing dependencies..."
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "${GREEN}[OK]${NC} Dependencies installed"

# ── 6. Create .env if missing ────────────────────────────────

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${YELLOW}[ACTION REQUIRED]${NC} Created .env from template"
    echo ""
    echo "  Edit .env and set your OpenAI API key (default provider):"
    echo "    OPENAI_API_KEY=sk-your_key_here   (get key at https://platform.openai.com)"
    echo ""
    echo "  Or switch to Ollama for free local inference:"
    echo "    LLM_PROVIDER=ollama               (no key needed, run: ollama pull llama3.1:8b)"
    echo ""
else
    echo -e "${GREEN}[OK]${NC} .env file exists"
fi

# ── 7. Done ──────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════"
echo -e "  ${GREEN}Setup complete!${NC}"
echo ""
echo "  To start the server:"
echo "    source .venv/bin/activate"
echo "    python app.py"
echo ""
echo "  Then test with:"
echo "    curl -X POST http://localhost:8000/analyze \\"
echo "      -F 'file=@samples/sample_transcript.txt'"
echo ""
echo "  API docs at: http://localhost:8000/docs"
echo "══════════════════════════════════════════════════"
echo ""
