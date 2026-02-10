package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"

	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/alfagnish/ollqd-gateway/internal/tasks"
	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// SMBShare represents a saved SMB share configuration stored in memory.
type SMBShare struct {
	ID       string `json:"id"`
	Server   string `json:"server"`
	Share    string `json:"share"`
	Username string `json:"username"`
	Password string `json:"password,omitempty"`
	Domain   string `json:"domain"`
	Port     int32  `json:"port"`
	Label    string `json:"label"`
}

// SMBHandler manages SMB share configurations and proxies browse/test
// requests to the gRPC SMBService.
type SMBHandler struct {
	grpc   *grpcclient.Client
	tm     *tasks.Manager
	mu     sync.RWMutex
	shares map[string]*SMBShare
}

// NewSMBHandler creates a new SMBHandler with an empty share store.
func NewSMBHandler(gc *grpcclient.Client, tm *tasks.Manager) *SMBHandler {
	return &SMBHandler{
		grpc:   gc,
		tm:     tm,
		shares: make(map[string]*SMBShare),
	}
}

// Routes registers all SMB routes on the given chi router.
func (h *SMBHandler) Routes(r chi.Router) {
	r.Get("/shares", h.ListShares)
	r.Post("/shares", h.AddShare)
	r.Delete("/shares/{id}", h.RemoveShare)
	r.Post("/shares/test", h.TestConnection)
	r.Post("/shares/{id}/browse", h.Browse)
	r.Post("/shares/{id}/index", h.Index)
}

// ListShares returns all saved SMB shares.
func (h *SMBHandler) ListShares(w http.ResponseWriter, r *http.Request) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	shares := make([]*SMBShare, 0, len(h.shares))
	for _, s := range h.shares {
		// Return a copy without the password.
		cp := *s
		cp.Password = ""
		shares = append(shares, &cp)
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"shares": shares,
		"count":  len(shares),
	})
}

// AddShare saves a new SMB share configuration.
func (h *SMBHandler) AddShare(w http.ResponseWriter, r *http.Request) {
	var req SMBShare
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	req.ID = uuid.New().String()
	if req.Port == 0 {
		req.Port = 445
	}

	h.mu.Lock()
	h.shares[req.ID] = &req
	h.mu.Unlock()

	// Return without password.
	resp := req
	resp.Password = ""

	writeJSON(w, http.StatusCreated, resp)
}

// RemoveShare deletes a saved SMB share by ID.
func (h *SMBHandler) RemoveShare(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")

	h.mu.Lock()
	_, exists := h.shares[id]
	if exists {
		delete(h.shares, id)
	}
	h.mu.Unlock()

	if !exists {
		writeError(w, http.StatusNotFound, fmt.Sprintf("share %s not found", id))
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"deleted": id})
}

// TestConnection tests connectivity to an SMB share via gRPC.
func (h *SMBHandler) TestConnection(w http.ResponseWriter, r *http.Request) {
	if h.grpc.SMB == nil {
		writeError(w, http.StatusServiceUnavailable, "smb service not available")
		return
	}

	var req struct {
		Server   string `json:"server"`
		Share    string `json:"share"`
		Username string `json:"username"`
		Password string `json:"password"`
		Domain   string `json:"domain"`
		Port     int32  `json:"port"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.SMB.TestConnection(r.Context(), &grpcclient.SMBTestRequest{
		Server:   req.Server,
		Share:    req.Share,
		Username: req.Username,
		Password: req.Password,
		Domain:   req.Domain,
		Port:     req.Port,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// Browse lists files in a remote SMB path using a saved share's credentials.
func (h *SMBHandler) Browse(w http.ResponseWriter, r *http.Request) {
	if h.grpc.SMB == nil {
		writeError(w, http.StatusServiceUnavailable, "smb service not available")
		return
	}

	id := chi.URLParam(r, "id")

	h.mu.RLock()
	share, exists := h.shares[id]
	h.mu.RUnlock()

	if !exists {
		writeError(w, http.StatusNotFound, fmt.Sprintf("share %s not found", id))
		return
	}

	var req struct {
		Path string `json:"path"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.SMB.Browse(r.Context(), &grpcclient.SMBBrowseRequest{
		Server:   share.Server,
		Share:    share.Share,
		Username: share.Username,
		Password: share.Password,
		Domain:   share.Domain,
		Port:     share.Port,
		Path:     req.Path,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

// Index starts a background task to index files from a saved SMB share.
func (h *SMBHandler) Index(w http.ResponseWriter, r *http.Request) {
	if h.grpc.Indexing == nil {
		writeError(w, http.StatusServiceUnavailable, "indexing service not available")
		return
	}

	id := chi.URLParam(r, "id")

	h.mu.RLock()
	share, exists := h.shares[id]
	h.mu.RUnlock()

	if !exists {
		writeError(w, http.StatusNotFound, fmt.Sprintf("share %s not found", id))
		return
	}

	var req struct {
		RemotePaths  []string `json:"remote_paths"`
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
		"share_id":      id,
		"remote_paths":  req.RemotePaths,
		"collection":    req.Collection,
		"chunk_size":    req.ChunkSize,
		"chunk_overlap": req.ChunkOverlap,
		"source_tag":    req.SourceTag,
		"server":        share.Server,
		"share":         share.Share,
		"username":      share.Username,
		"password":      share.Password,
		"domain":        share.Domain,
		"port":          share.Port,
	}

	taskID := h.tm.Create("index_smb", params)
	h.tm.Start(taskID)

	ctx, cancel := context.WithCancel(context.Background())
	h.tm.SetCancelFunc(taskID, cancel)

	go func() {
		stream, err := h.grpc.Indexing.IndexSMBFiles(ctx, &grpcclient.IndexSMBFilesRequest{
			ShareId:      id,
			RemotePaths:  req.RemotePaths,
			Collection:   req.Collection,
			ChunkSize:    req.ChunkSize,
			ChunkOverlap: req.ChunkOverlap,
			SourceTag:    req.SourceTag,
			Server:       share.Server,
			Share:        share.Share,
			Username:     share.Username,
			Password:     share.Password,
			Domain:       share.Domain,
			Port:         share.Port,
		})
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
			if err != nil {
				if err == io.EOF {
					h.tm.Complete(taskID, nil)
				} else {
					h.tm.Fail(taskID, fmt.Sprintf("stream error: %v", err))
				}
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
				log.Printf("[smb task %s] unknown status: %s", taskID, progress.Status)
			}
		}
	}()

	writeJSON(w, http.StatusAccepted, map[string]interface{}{
		"task_id": taskID,
		"status":  "started",
	})
}
