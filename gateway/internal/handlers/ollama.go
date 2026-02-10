package handlers

import (
	"net/http"
	"net/http/httputil"

	"github.com/go-chi/chi/v5"
)

// OllamaHandler mounts the Ollama reverse proxy at /api/ollama/*.
type OllamaHandler struct {
	proxy *httputil.ReverseProxy
}

// NewOllamaHandler wraps an existing Ollama reverse proxy.
func NewOllamaHandler(proxy *httputil.ReverseProxy) *OllamaHandler {
	return &OllamaHandler{proxy: proxy}
}

// Routes registers the catch-all proxy route. The prefix stripping is
// handled inside the proxy's Director function (see proxy/ollama.go).
func (h *OllamaHandler) Routes(r chi.Router) {
	r.HandleFunc("/*", func(w http.ResponseWriter, r *http.Request) {
		h.proxy.ServeHTTP(w, r)
	})
}
