# MY PERSONAL AI

An intelligent, autonomous personal AI system featuring:
- **Hybrid Intelligence:** Intelligent automatic routing between local models (Ollama / Qwen / Llama) and frontier cloud models (Gemini / Claude / OpenAI) to optimize speed, privacy, and token cost.
- **Modular Multi-Agent Architecture:** Specialized agents for Coding, Research, Cybersecurity, System/Computer Use, Data Analysis, and Testing.
- **Tri-Layer Sovereign Memory:** Working scratchpad, agent experiential memory, and persistent central knowledge.
- **Cross-Platform Integration:** Desktop automation and Android phone integration via ADB.

## Quick Start (Phase 1)
1. Initialize virtual environment:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```
2. Configure environment:
   ```bash
   cp .env.example .env
   ```
3. Run local server:
   ```bash
   python server.py
   ```
