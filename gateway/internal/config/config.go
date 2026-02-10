package config

import (
	"os"
	"strconv"
)

// Config holds all gateway configuration loaded from environment variables.
type Config struct {
	ListenAddr      string // HTTP listen address
	WorkerAddr      string // Python gRPC worker address
	OllamaURL       string // Ollama API base URL
	QdrantURL       string // Qdrant API base URL
	UploadDir       string // Directory for uploaded files
	MaxUploadSizeMB int64  // Maximum upload size in megabytes
	DockerSocket    string // Docker socket path for container management
}

// Load reads configuration from environment variables, falling back to defaults.
func Load() *Config {
	return &Config{
		ListenAddr:      envOrDefault("LISTEN_ADDR", ":8000"),
		WorkerAddr:      envOrDefault("WORKER_ADDR", "localhost:50051"),
		OllamaURL:       envOrDefault("OLLAMA_URL", "http://localhost:11434"),
		QdrantURL:       envOrDefault("QDRANT_URL", "http://localhost:6333"),
		UploadDir:       envOrDefault("UPLOAD_DIR", "/uploads"),
		MaxUploadSizeMB: envOrDefaultInt64("MAX_UPLOAD_SIZE_MB", 50),
		DockerSocket:    envOrDefault("DOCKER_SOCKET", "/var/run/docker.sock"),
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envOrDefaultInt64(key string, fallback int64) int64 {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		return fallback
	}
	return n
}
