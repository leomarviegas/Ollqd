package handlers

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"

	"github.com/go-chi/chi/v5"
)

// OllamaHandler provides both a reverse proxy for raw Ollama API access and
// dedicated REST handlers that translate clean URLs to Ollama's actual API.
type OllamaHandler struct {
	proxy   *httputil.ReverseProxy
	baseURL string
	client  *http.Client
}

// NewOllamaHandler wraps an existing Ollama reverse proxy and adds
// dedicated model-management handlers.
func NewOllamaHandler(proxy *httputil.ReverseProxy, baseURL string) *OllamaHandler {
	return &OllamaHandler{
		proxy:   proxy,
		baseURL: baseURL,
		client:  &http.Client{Timeout: 0}, // no timeout for streaming (pull)
	}
}

// Routes registers model-management routes and the catch-all proxy.
// Specific routes are matched first; everything else falls through to the proxy.
func (h *OllamaHandler) Routes(r chi.Router) {
	r.Get("/models", h.ListModels)
	r.Get("/ps", h.RunningModels)
	r.Post("/models/show", h.ShowModel)
	r.Post("/models/pull", h.PullModel)
	r.Delete("/models/{name}", h.DeleteModel)
	r.HandleFunc("/*", func(w http.ResponseWriter, r *http.Request) {
		h.proxy.ServeHTTP(w, r)
	})
}

// ListModels translates GET /api/ollama/models → GET /api/tags on Ollama.
func (h *OllamaHandler) ListModels(w http.ResponseWriter, r *http.Request) {
	resp, err := h.client.Get(h.baseURL + "/api/tags")
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("ollama error: %v", err))
		return
	}
	defer resp.Body.Close()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

// RunningModels translates GET /api/ollama/ps → GET /api/ps on Ollama.
func (h *OllamaHandler) RunningModels(w http.ResponseWriter, r *http.Request) {
	resp, err := h.client.Get(h.baseURL + "/api/ps")
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("ollama error: %v", err))
		return
	}
	defer resp.Body.Close()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

// ShowModel translates POST /api/ollama/models/show → POST /api/show on Ollama.
func (h *OllamaHandler) ShowModel(w http.ResponseWriter, r *http.Request) {
	resp, err := h.client.Post(h.baseURL+"/api/show", "application/json", r.Body)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("ollama error: %v", err))
		return
	}
	defer resp.Body.Close()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

// PullModel translates POST /api/ollama/models/pull → POST /api/pull on Ollama.
// The response is streamed back as SSE for progress tracking.
func (h *OllamaHandler) PullModel(w http.ResponseWriter, r *http.Request) {
	// Read and wrap the request body — Ollama expects {"name": "..."} with
	// optional "stream": true. We forward the body as-is.
	body, err := io.ReadAll(r.Body)
	if err != nil {
		writeError(w, http.StatusBadRequest, "failed to read body")
		return
	}

	req, err := http.NewRequestWithContext(r.Context(), "POST", h.baseURL+"/api/pull", bytes.NewReader(body))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := h.client.Do(req)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("ollama error: %v", err))
		return
	}
	defer resp.Body.Close()

	// Stream the response as SSE events.
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.WriteHeader(http.StatusOK)

	flusher, _ := w.(http.Flusher)
	buf := make([]byte, 4096)
	for {
		n, readErr := resp.Body.Read(buf)
		if n > 0 {
			// Ollama streams newline-delimited JSON. Wrap each line as SSE.
			lines := bytes.Split(buf[:n], []byte("\n"))
			for _, line := range lines {
				line = bytes.TrimSpace(line)
				if len(line) == 0 {
					continue
				}
				fmt.Fprintf(w, "data: %s\n\n", line)
				if flusher != nil {
					flusher.Flush()
				}
			}
		}
		if readErr != nil {
			if readErr != io.EOF {
				fmt.Fprintf(w, "data: {\"error\":\"%s\"}\n\n", readErr.Error())
			}
			fmt.Fprintf(w, "data: [DONE]\n\n")
			if flusher != nil {
				flusher.Flush()
			}
			return
		}
	}
}

// DeleteModel translates DELETE /api/ollama/models/{name} → DELETE /api/delete
// on Ollama with body {"name": "..."}.
func (h *OllamaHandler) DeleteModel(w http.ResponseWriter, r *http.Request) {
	rawName := chi.URLParam(r, "name")
	if rawName == "" {
		writeError(w, http.StatusBadRequest, "model name is required")
		return
	}
	name, _ := url.PathUnescape(rawName)

	body, _ := json.Marshal(map[string]string{"name": name})
	req, err := http.NewRequestWithContext(r.Context(), "DELETE", h.baseURL+"/api/delete", bytes.NewReader(body))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := (&http.Client{Timeout: 30 * time.Second}).Do(req)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("ollama error: %v", err))
		return
	}
	defer resp.Body.Close()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}
