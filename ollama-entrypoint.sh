#!/bin/bash
# Start ollama server in background
ollama serve &
SERVE_PID=$!

# Wait for server to be ready
echo "[ollqd] Waiting for Ollama server..."
until ollama list >/dev/null 2>&1; do
    sleep 1
done
echo "[ollqd] Ollama server ready."

# Sign in if auth keys don't exist yet
if [ ! -f /root/.ollama/id_ed25519 ]; then
    echo ""
    echo "============================================"
    echo "  Ollama Cloud sign-in required."
    echo "  Run this in another terminal:"
    echo ""
    echo "    docker exec -it ollqd-ollama ollama signin"
    echo ""
    echo "  Auth persists across restarts."
    echo "============================================"
    echo ""
else
    echo "[ollqd] Ollama Cloud auth found."
fi

# Keep server running
wait $SERVE_PID
