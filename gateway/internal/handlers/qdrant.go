package handlers

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strconv"

	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/go-chi/chi/v5"
)

// QdrantHandler provides both a reverse proxy for raw Qdrant API access and
// dedicated REST handlers that translate clean URLs to Qdrant's actual API.
type QdrantHandler struct {
	proxy   *httputil.ReverseProxy
	baseURL string
	client  *http.Client
	grpc    *grpcclient.Client
}

// NewQdrantHandler wraps an existing Qdrant reverse proxy and adds
// dedicated collection-management handlers.
func NewQdrantHandler(proxy *httputil.ReverseProxy, baseURL string, gc *grpcclient.Client) *QdrantHandler {
	return &QdrantHandler{
		proxy:   proxy,
		baseURL: baseURL,
		client:  &http.Client{},
		grpc:    gc,
	}
}

// Routes registers collection-management routes and the catch-all proxy.
func (h *QdrantHandler) Routes(r chi.Router) {
	r.Get("/collections", h.ListCollections)
	r.Post("/collections", h.CreateCollection)
	r.Delete("/collections/{name}", h.DeleteCollection)
	r.Get("/collections/{name}/points", h.BrowsePoints)
	r.Post("/collections/{name}/search", h.SearchCollection)
	r.HandleFunc("/*", func(w http.ResponseWriter, r *http.Request) {
		h.proxy.ServeHTTP(w, r)
	})
}

// ListCollections returns all collections from Qdrant.
func (h *QdrantHandler) ListCollections(w http.ResponseWriter, r *http.Request) {
	resp, err := h.client.Get(h.baseURL + "/collections")
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("qdrant error: %v", err))
		return
	}
	defer resp.Body.Close()

	var raw map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		writeError(w, http.StatusBadGateway, "failed to parse qdrant response")
		return
	}

	// Flatten: Qdrant returns {result: {collections: [...]}} → we return {collections: [...]}
	result, _ := raw["result"].(map[string]interface{})
	collections, _ := result["collections"].([]interface{})
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"collections": collections,
	})
}

// CreateCollection translates POST {name, vector_size, distance} →
// PUT /collections/{name} {vectors: {size, distance}} on Qdrant.
func (h *QdrantHandler) CreateCollection(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name       string `json:"name"`
		VectorSize int    `json:"vector_size"`
		Distance   string `json:"distance"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	if req.VectorSize <= 0 {
		req.VectorSize = 1024
	}
	if req.Distance == "" {
		req.Distance = "Cosine"
	}

	// Qdrant expects PUT /collections/{name}
	body, _ := json.Marshal(map[string]interface{}{
		"vectors": map[string]interface{}{
			"size":     req.VectorSize,
			"distance": req.Distance,
		},
	})

	httpReq, err := http.NewRequestWithContext(r.Context(), "PUT",
		h.baseURL+"/collections/"+url.PathEscape(req.Name), bytes.NewReader(body))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := h.client.Do(httpReq)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("qdrant error: %v", err))
		return
	}
	defer resp.Body.Close()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

// DeleteCollection translates DELETE /collections/{name} to Qdrant.
func (h *QdrantHandler) DeleteCollection(w http.ResponseWriter, r *http.Request) {
	rawName := chi.URLParam(r, "name")
	name, _ := url.PathUnescape(rawName)

	httpReq, err := http.NewRequestWithContext(r.Context(), "DELETE",
		h.baseURL+"/collections/"+url.PathEscape(name), nil)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	resp, err := h.client.Do(httpReq)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("qdrant error: %v", err))
		return
	}
	defer resp.Body.Close()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

// BrowsePoints translates GET /collections/{name}/points?limit=N&offset=X →
// POST /collections/{name}/points/scroll on Qdrant.
func (h *QdrantHandler) BrowsePoints(w http.ResponseWriter, r *http.Request) {
	rawName := chi.URLParam(r, "name")
	name, _ := url.PathUnescape(rawName)

	limit := 20
	if l := r.URL.Query().Get("limit"); l != "" {
		if n, err := strconv.Atoi(l); err == nil && n > 0 {
			limit = n
		}
	}

	scrollBody := map[string]interface{}{
		"limit":        limit,
		"with_payload": true,
		"with_vector":  false,
	}
	if offset := r.URL.Query().Get("offset"); offset != "" {
		scrollBody["offset"] = offset
	}

	body, _ := json.Marshal(scrollBody)
	resp, err := h.client.Post(
		h.baseURL+"/collections/"+url.PathEscape(name)+"/points/scroll",
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("qdrant error: %v", err))
		return
	}
	defer resp.Body.Close()

	var raw map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		writeError(w, http.StatusBadGateway, "failed to parse qdrant response")
		return
	}

	// Flatten Qdrant response: {result: {points: [...], next_page_offset: X}}
	result, _ := raw["result"].(map[string]interface{})
	points, _ := result["points"].([]interface{})
	nextOffset := result["next_page_offset"]

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"points":      points,
		"next_offset": nextOffset,
	})
}

// SearchCollection uses the gRPC SearchService to perform semantic search
// (embed query text then search Qdrant). Falls back to error if gRPC unavailable.
func (h *QdrantHandler) SearchCollection(w http.ResponseWriter, r *http.Request) {
	rawName := chi.URLParam(r, "name")
	name, _ := url.PathUnescape(rawName)

	var req struct {
		Query string `json:"query"`
		TopK  int32  `json:"top_k"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.TopK <= 0 {
		req.TopK = 10
	}

	if h.grpc.Search == nil {
		writeError(w, http.StatusServiceUnavailable, "search service not available")
		return
	}

	resp, err := h.grpc.Search.SearchCollection(r.Context(), &grpcclient.SearchCollectionRequest{
		Collection: name,
		Query:      req.Query,
		TopK:       req.TopK,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}
