package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"

	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/alfagnish/ollqd-gateway/internal/tasks"
	"github.com/go-chi/chi/v5"
)

// RAGHandler provides endpoints for search, indexing, and visualization.
// Long-running indexing operations are tracked as background tasks.
type RAGHandler struct {
	grpc *grpcclient.Client
	tm   *tasks.Manager
}

// NewRAGHandler creates a new RAGHandler.
func NewRAGHandler(gc *grpcclient.Client, tm *tasks.Manager) *RAGHandler {
	return &RAGHandler{grpc: gc, tm: tm}
}

// Routes registers all RAG routes on the given chi router.
func (h *RAGHandler) Routes(r chi.Router) {
	r.Post("/search", h.Search)
	r.Post("/search/{collection}", h.SearchCollection)
	r.Post("/index/codebase", h.IndexCodebase)
	r.Post("/index/documents", h.IndexDocuments)
	r.Post("/index/images", h.IndexImages)
	r.Get("/visualize/{collection}/overview", h.VisualizeOverview)
	r.Get("/visualize/{collection}/file-tree", h.VisualizeFileTree)
	r.Get("/visualize/{collection}/vectors", h.VisualizeVectors)
}

// Search performs a global vector search across the default collection.
func (h *RAGHandler) Search(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Search == nil {
		writeError(w, http.StatusServiceUnavailable, "search service not available")
		return
	}

	var req struct {
		Query    string `json:"query"`
		TopK     int32  `json:"top_k"`
		Language string `json:"language"`
		FilePath string `json:"file_path"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Search.Search(r.Context(), &grpcclient.SearchRequest{
		Query:    req.Query,
		TopK:     req.TopK,
		Language: req.Language,
		FilePath: req.FilePath,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// SearchCollection performs a vector search scoped to a specific collection.
func (h *RAGHandler) SearchCollection(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Search == nil {
		writeError(w, http.StatusServiceUnavailable, "search service not available")
		return
	}

	collection := chi.URLParam(r, "collection")

	var req struct {
		Query    string `json:"query"`
		TopK     int32  `json:"top_k"`
		Language string `json:"language"`
		FilePath string `json:"file_path"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Search.SearchCollection(r.Context(), &grpcclient.SearchCollectionRequest{
		Collection: collection,
		Query:      req.Query,
		TopK:       req.TopK,
		Language:   req.Language,
		FilePath:   req.FilePath,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// IndexCodebase starts a background codebase indexing task.
func (h *RAGHandler) IndexCodebase(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Indexing == nil {
		writeError(w, http.StatusServiceUnavailable, "indexing service not available")
		return
	}

	var req struct {
		RootPath      string   `json:"root_path"`
		Collection    string   `json:"collection"`
		Incremental   bool     `json:"incremental"`
		ChunkSize     int32    `json:"chunk_size"`
		ChunkOverlap  int32    `json:"chunk_overlap"`
		ExtraSkipDirs []string `json:"extra_skip_dirs"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	// Store params for potential retry.
	params := map[string]interface{}{
		"root_path":       req.RootPath,
		"collection":      req.Collection,
		"incremental":     req.Incremental,
		"chunk_size":      req.ChunkSize,
		"chunk_overlap":   req.ChunkOverlap,
		"extra_skip_dirs": req.ExtraSkipDirs,
	}

	taskID := h.tm.Create("index_codebase", params)
	h.tm.Start(taskID)

	// Launch the gRPC stream in a background goroutine.
	ctx, cancel := context.WithCancel(context.Background())
	h.tm.SetCancelFunc(taskID, cancel)

	go h.runIndexStream(ctx, taskID, func() (grpcclient.IndexingStream, error) {
		return h.grpc.Indexing.IndexCodebase(ctx, &grpcclient.IndexCodebaseRequest{
			RootPath:      req.RootPath,
			Collection:    req.Collection,
			Incremental:   req.Incremental,
			ChunkSize:     req.ChunkSize,
			ChunkOverlap:  req.ChunkOverlap,
			ExtraSkipDirs: req.ExtraSkipDirs,
		})
	})

	writeJSON(w, http.StatusAccepted, map[string]interface{}{
		"task_id": taskID,
		"status":  "started",
	})
}

// IndexDocuments starts a background document indexing task.
func (h *RAGHandler) IndexDocuments(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Indexing == nil {
		writeError(w, http.StatusServiceUnavailable, "indexing service not available")
		return
	}

	var req struct {
		Paths        []string `json:"paths"`
		Collection   string   `json:"collection"`
		ChunkSize    int32    `json:"chunk_size"`
		ChunkOverlap int32    `json:"chunk_overlap"`
		SourceTag    string   `json:"source_tag"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	params := map[string]interface{}{
		"paths":         req.Paths,
		"collection":    req.Collection,
		"chunk_size":    req.ChunkSize,
		"chunk_overlap": req.ChunkOverlap,
		"source_tag":    req.SourceTag,
	}

	taskID := h.tm.Create("index_documents", params)
	h.tm.Start(taskID)

	ctx, cancel := context.WithCancel(context.Background())
	h.tm.SetCancelFunc(taskID, cancel)

	go h.runIndexStream(ctx, taskID, func() (grpcclient.IndexingStream, error) {
		return h.grpc.Indexing.IndexDocuments(ctx, &grpcclient.IndexDocumentsRequest{
			Paths:        req.Paths,
			Collection:   req.Collection,
			ChunkSize:    req.ChunkSize,
			ChunkOverlap: req.ChunkOverlap,
			SourceTag:    req.SourceTag,
		})
	})

	writeJSON(w, http.StatusAccepted, map[string]interface{}{
		"task_id": taskID,
		"status":  "started",
	})
}

// IndexImages starts a background image indexing task.
func (h *RAGHandler) IndexImages(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Indexing == nil {
		writeError(w, http.StatusServiceUnavailable, "indexing service not available")
		return
	}

	var req struct {
		RootPath       string   `json:"root_path"`
		Collection     string   `json:"collection"`
		VisionModel    string   `json:"vision_model"`
		CaptionPrompt  string   `json:"caption_prompt"`
		Incremental    bool     `json:"incremental"`
		MaxImageSizeKB int32    `json:"max_image_size_kb"`
		ExtraSkipDirs  []string `json:"extra_skip_dirs"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	params := map[string]interface{}{
		"root_path":         req.RootPath,
		"collection":        req.Collection,
		"vision_model":      req.VisionModel,
		"caption_prompt":    req.CaptionPrompt,
		"incremental":       req.Incremental,
		"max_image_size_kb": req.MaxImageSizeKB,
		"extra_skip_dirs":   req.ExtraSkipDirs,
	}

	taskID := h.tm.Create("index_images", params)
	h.tm.Start(taskID)

	ctx, cancel := context.WithCancel(context.Background())
	h.tm.SetCancelFunc(taskID, cancel)

	go h.runIndexStream(ctx, taskID, func() (grpcclient.IndexingStream, error) {
		return h.grpc.Indexing.IndexImages(ctx, &grpcclient.IndexImagesRequest{
			RootPath:       req.RootPath,
			Collection:     req.Collection,
			VisionModel:    req.VisionModel,
			CaptionPrompt:  req.CaptionPrompt,
			Incremental:    req.Incremental,
			MaxImageSizeKb: req.MaxImageSizeKB,
			ExtraSkipDirs:  req.ExtraSkipDirs,
		})
	})

	writeJSON(w, http.StatusAccepted, map[string]interface{}{
		"task_id": taskID,
		"status":  "started",
	})
}

// runIndexStream consumes a gRPC server stream and updates the task manager
// with progress events. On completion or error the task is marked accordingly.
func (h *RAGHandler) runIndexStream(ctx context.Context, taskID string, openStream func() (grpcclient.IndexingStream, error)) {
	stream, err := openStream()
	if err != nil {
		h.tm.Fail(taskID, fmt.Sprintf("failed to open stream: %v", err))
		return
	}
	defer stream.Close()

	for {
		select {
		case <-ctx.Done():
			h.tm.Fail(taskID, "cancelled")
			return
		default:
		}

		progress, err := stream.Recv()
		if err == io.EOF {
			// Stream ended without an explicit completed message; mark done.
			h.tm.Complete(taskID, nil)
			return
		}
		if err != nil {
			h.tm.Fail(taskID, fmt.Sprintf("stream error: %v", err))
			return
		}

		switch progress.Status {
		case "running":
			h.tm.UpdateProgress(taskID, float64(progress.Progress), "running")
		case "completed":
			h.tm.Complete(taskID, progress.Result)
			return
		case "failed":
			h.tm.Fail(taskID, progress.Error)
			return
		case "cancelled":
			h.tm.Cancel(taskID)
			return
		default:
			log.Printf("[task %s] unknown status: %s", taskID, progress.Status)
		}
	}
}

// VisualizeOverview returns a force-graph overview for a collection.
func (h *RAGHandler) VisualizeOverview(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Visualization == nil {
		writeError(w, http.StatusServiceUnavailable, "visualization service not available")
		return
	}

	collection := chi.URLParam(r, "collection")
	limit := int32(200)
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			limit = int32(n)
		}
	}

	resp, err := h.grpc.Visualization.Overview(r.Context(), &grpcclient.OverviewRequest{
		Collection: collection,
		Limit:      limit,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// VisualizeFileTree returns a file-tree visualization for a collection.
func (h *RAGHandler) VisualizeFileTree(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Visualization == nil {
		writeError(w, http.StatusServiceUnavailable, "visualization service not available")
		return
	}

	collection := chi.URLParam(r, "collection")
	filePath := r.URL.Query().Get("file_path")

	resp, err := h.grpc.Visualization.FileTree(r.Context(), &grpcclient.FileTreeRequest{
		Collection: collection,
		FilePath:   filePath,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// VisualizeVectors returns PCA/t-SNE reduced vector data for a collection.
func (h *RAGHandler) VisualizeVectors(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Visualization == nil {
		writeError(w, http.StatusServiceUnavailable, "visualization service not available")
		return
	}

	collection := chi.URLParam(r, "collection")
	method := r.URL.Query().Get("method")
	if method == "" {
		method = "pca"
	}
	dims := int32(2)
	if v := r.URL.Query().Get("dims"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			dims = int32(n)
		}
	}
	limit := int32(500)
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			limit = int32(n)
		}
	}

	resp, err := h.grpc.Visualization.Vectors(r.Context(), &grpcclient.VectorsRequest{
		Collection: collection,
		Method:     method,
		Dims:       dims,
		Limit:      limit,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}
