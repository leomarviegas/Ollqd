package handlers

import (
	"net/http"
	"net/http/httputil"

	"github.com/go-chi/chi/v5"
)

// QdrantHandler mounts the Qdrant reverse proxy at /api/qdrant/*.
type QdrantHandler struct {
	proxy *httputil.ReverseProxy
}

// NewQdrantHandler wraps an existing Qdrant reverse proxy.
func NewQdrantHandler(proxy *httputil.ReverseProxy) *QdrantHandler {
	return &QdrantHandler{proxy: proxy}
}

// Routes registers the catch-all proxy route. The prefix stripping is
// handled inside the proxy's Director function (see proxy/qdrant.go).
func (h *QdrantHandler) Routes(r chi.Router) {
	r.HandleFunc("/*", func(w http.ResponseWriter, r *http.Request) {
		h.proxy.ServeHTTP(w, r)
	})
}
