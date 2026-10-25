#!/bin/sh
set -eu

# Same limits as the optional macOS LaunchAgent; model data stays outside Desktop.
task_ollama_bin=${OLLAMA_BIN:-/opt/homebrew/bin/ollama}
task_models_dir=${ALFA_CREDIT_LLM_DIR:-"$HOME/Library/Application Support/AlfaCredit/ollama-models"}
if [ ! -x "$task_ollama_bin" ]; then
    echo "Install Ollama and set OLLAMA_BIN to its executable path." >&2
    exit 1
fi
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS="$task_models_dir"
export OLLAMA_NO_CLOUD=1
export OLLAMA_CONTEXT_LENGTH=8192
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_MAX_QUEUE=2
export OLLAMA_KEEP_ALIVE=2m
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
exec "$task_ollama_bin" serve
