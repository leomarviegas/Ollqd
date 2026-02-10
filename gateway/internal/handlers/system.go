package handlers

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/alfagnish/ollqd-gateway/internal/config"
	"github.com/alfagnish/ollqd-gateway/internal/docker"
	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/go-chi/chi/v5"
)

// SystemHandler provides endpoints for health checks and configuration
// management. It proxies config-related requests to the Python gRPC worker.
type SystemHandler struct {
	cfg      *config.Config
	grpc     *grpcclient.Client
	httpCli  *http.Client
	docker   *docker.Manager
}

// NewSystemHandler creates a new SystemHandler.
func NewSystemHandler(cfg *config.Config, gc *grpcclient.Client, dm *docker.Manager) *SystemHandler {
	return &SystemHandler{
		cfg:     cfg,
		grpc:    gc,
		httpCli: &http.Client{Timeout: 5 * time.Second},
		docker:  dm,
	}
}

// Routes registers all system routes on the given chi router.
func (h *SystemHandler) Routes(r chi.Router) {
	r.Get("/health", h.Health)
	r.Get("/config", h.GetConfig)
	r.Put("/config/mounted-paths", h.UpdateMountedPaths)
	r.Get("/config/embedding", h.GetEmbeddingInfo)
	r.Put("/config/embedding", h.SetEmbeddingModel)
	r.Post("/config/embedding/test", h.TestEmbed)
	r.Post("/config/embedding/compare", h.CompareModels)
	r.Get("/config/pii", h.GetPIIConfig)
	r.Put("/config/pii", h.UpdatePII)
	r.Post("/config/pii/test", h.TestMasking)
	r.Get("/config/docling", h.GetDoclingConfig)
	r.Put("/config/docling", h.UpdateDocling)
	r.Put("/config/distance", h.UpdateDistance)
	r.Put("/config/ollama", h.UpdateOllama)
	r.Put("/config/qdrant", h.UpdateQdrant)
	r.Put("/config/chunking", h.UpdateChunking)
	r.Put("/config/image", h.UpdateImage)
	r.Delete("/config/{section}", h.ResetConfig)
	r.Get("/ollama/container", h.OllamaContainerStatus)
	r.Post("/ollama/container", h.ManageOllamaContainer)
}

// serviceStatus is used by the Health endpoint to report the health of
// upstream services.
type serviceStatus struct {
	Status  string `json:"status"`
	URL     string `json:"url,omitempty"`
	Latency string `json:"latency,omitempty"`
	Error   string `json:"error,omitempty"`
}

// Health pings Ollama and Qdrant to report service status.
// Accepts optional query params ?ollama_url=...&qdrant_url=... to check arbitrary hosts.
func (h *SystemHandler) Health(w http.ResponseWriter, r *http.Request) {
	ollamaURL := r.URL.Query().Get("ollama_url")
	if ollamaURL == "" {
		ollamaURL = h.cfg.OllamaURL
	}
	qdrantURL := r.URL.Query().Get("qdrant_url")
	if qdrantURL == "" {
		qdrantURL = h.cfg.QdrantURL
	}

	ollamaStatus := h.pingService(ollamaURL + "/api/tags")
	ollamaStatus.URL = ollamaURL
	qdrantStatus := h.pingService(qdrantURL + "/collections")
	qdrantStatus.URL = qdrantURL

	overall := "ok"
	if ollamaStatus.Error != "" || qdrantStatus.Error != "" {
		overall = "degraded"
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"status": overall,
		"ollama": ollamaStatus,
		"qdrant": qdrantStatus,
	})
}

func (h *SystemHandler) pingService(url string) serviceStatus {
	start := time.Now()
	resp, err := h.httpCli.Get(url)
	latency := time.Since(start)

	if err != nil {
		return serviceStatus{
			Status:  "error",
			Latency: latency.String(),
			Error:   err.Error(),
		}
	}
	defer resp.Body.Close()
	io.ReadAll(resp.Body)

	return serviceStatus{
		Status:  "ok",
		Latency: latency.String(),
	}
}

// GetConfig retrieves the full application config from the gRPC worker.
func (h *SystemHandler) GetConfig(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	cfg, err := h.grpc.Config.GetConfig(r.Context())
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, cfg)
}

// UpdateMountedPaths updates the list of mounted paths in the config.
func (h *SystemHandler) UpdateMountedPaths(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	var req struct {
		Paths []string `json:"paths"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Config.UpdateMountedPaths(r.Context(), &grpcclient.UpdateMountedPathsRequest{
		Paths: req.Paths,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// GetEmbeddingInfo returns current embedding model information.
func (h *SystemHandler) GetEmbeddingInfo(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Embedding == nil {
		writeError(w, http.StatusServiceUnavailable, "embedding service not available")
		return
	}

	info, err := h.grpc.Embedding.GetInfo(r.Context())
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, info)
}

// SetEmbeddingModel changes the active embedding model.
func (h *SystemHandler) SetEmbeddingModel(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Embedding == nil {
		writeError(w, http.StatusServiceUnavailable, "embedding service not available")
		return
	}

	var req struct {
		Model string `json:"model"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Embedding.SetModel(r.Context(), &grpcclient.SetEmbedModelRequest{
		Model: req.Model,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// TestEmbed runs a test embedding for the given text.
func (h *SystemHandler) TestEmbed(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Embedding == nil {
		writeError(w, http.StatusServiceUnavailable, "embedding service not available")
		return
	}

	var req struct {
		Text string `json:"text"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Embedding.TestEmbed(r.Context(), &grpcclient.TestEmbedRequest{
		Text: req.Text,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// CompareModels runs test embeddings with two different models and returns comparison.
func (h *SystemHandler) CompareModels(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Embedding == nil {
		writeError(w, http.StatusServiceUnavailable, "embedding service not available")
		return
	}

	var req struct {
		Text   string `json:"text"`
		Model1 string `json:"model1"`
		Model2 string `json:"model2"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Embedding.CompareModels(r.Context(), &grpcclient.CompareModelsRequest{
		Text:   req.Text,
		Model1: req.Model1,
		Model2: req.Model2,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// GetPIIConfig returns current PII masking configuration.
func (h *SystemHandler) GetPIIConfig(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	resp, err := h.grpc.Config.GetPIIConfig(r.Context())
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// UpdatePII updates the PII masking configuration.
func (h *SystemHandler) UpdatePII(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	var req grpcclient.UpdatePIIRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Config.UpdatePII(r.Context(), &req)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// TestMasking tests PII masking on sample text.
func (h *SystemHandler) TestMasking(w http.ResponseWriter, r *http.Request) {
	if h.grpc.PII == nil {
		writeError(w, http.StatusServiceUnavailable, "pii service not available")
		return
	}

	var req struct {
		Text string `json:"text"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.PII.TestMasking(r.Context(), &grpcclient.TestMaskingRequest{
		Text: req.Text,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// GetDoclingConfig returns current Docling document processing configuration.
func (h *SystemHandler) GetDoclingConfig(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	resp, err := h.grpc.Config.GetDoclingConfig(r.Context())
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// UpdateDocling updates the Docling document processing configuration.
func (h *SystemHandler) UpdateDocling(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	var req grpcclient.UpdateDoclingRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Config.UpdateDocling(r.Context(), &req)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// UpdateDistance updates the default vector distance metric.
func (h *SystemHandler) UpdateDistance(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	var req struct {
		Distance string `json:"distance"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Config.UpdateDistance(r.Context(), &grpcclient.UpdateDistanceRequest{
		Distance: req.Distance,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// UpdateOllama updates the Ollama configuration.
func (h *SystemHandler) UpdateOllama(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	var req grpcclient.UpdateOllamaRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Config.UpdateOllama(r.Context(), &req)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// UpdateQdrant updates the Qdrant configuration.
func (h *SystemHandler) UpdateQdrant(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	var req grpcclient.UpdateQdrantRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Config.UpdateQdrant(r.Context(), &req)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// UpdateChunking updates the chunking configuration.
func (h *SystemHandler) UpdateChunking(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	var req grpcclient.UpdateChunkingRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Config.UpdateChunking(r.Context(), &req)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// UpdateImage updates the image configuration.
func (h *SystemHandler) UpdateImage(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	var req grpcclient.UpdateImageRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Config.UpdateImage(r.Context(), &req)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// ResetConfig deletes persisted config overrides for a section, reverting to defaults.
func (h *SystemHandler) ResetConfig(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Config == nil {
		writeError(w, http.StatusServiceUnavailable, "config service not available")
		return
	}

	section := chi.URLParam(r, "section")
	if section == "all" {
		section = ""
	}

	resp, err := h.grpc.Config.ResetConfig(r.Context(), &grpcclient.ResetConfigRequest{
		Section: section,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

const ollamaContainerName = "ollqd-ollama"

// OllamaContainerStatus returns the Docker container status for the local Ollama instance.
func (h *SystemHandler) OllamaContainerStatus(w http.ResponseWriter, r *http.Request) {
	if h.docker == nil {
		writeJSON(w, http.StatusOK, map[string]string{"status": "unavailable"})
		return
	}

	status, err := h.docker.ContainerStatus(r.Context(), ollamaContainerName)
	if err != nil {
		writeError(w, http.StatusInternalServerError, fmt.Sprintf("docker error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": status})
}

// ManageOllamaContainer starts or stops the local Ollama Docker container.
func (h *SystemHandler) ManageOllamaContainer(w http.ResponseWriter, r *http.Request) {
	if h.docker == nil {
		writeError(w, http.StatusServiceUnavailable, "docker not available")
		return
	}

	var req struct {
		Action string `json:"action"` // "start" or "stop"
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	ctx := r.Context()

	switch req.Action {
	case "start":
		if err := h.docker.EnsureContainer(ctx, ollamaContainerName); err != nil {
			writeError(w, http.StatusInternalServerError, fmt.Sprintf("ensure container: %v", err))
			return
		}
		if err := h.docker.StartContainer(ctx, ollamaContainerName); err != nil {
			writeError(w, http.StatusInternalServerError, fmt.Sprintf("start container: %v", err))
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "running", "action": "started"})

	case "stop":
		if err := h.docker.StopContainer(ctx, ollamaContainerName); err != nil {
			writeError(w, http.StatusInternalServerError, fmt.Sprintf("stop container: %v", err))
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "stopped", "action": "stopped"})

	default:
		writeError(w, http.StatusBadRequest, "action must be 'start' or 'stop'")
	}
}
