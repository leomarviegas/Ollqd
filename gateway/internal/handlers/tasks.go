package handlers

import (
	"context"
	"fmt"
	"io"
	"net/http"

	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/alfagnish/ollqd-gateway/internal/tasks"
	"github.com/go-chi/chi/v5"
)

// TasksHandler provides endpoints for listing, inspecting, cancelling,
// retrying, and clearing background tasks.
type TasksHandler struct {
	grpc *grpcclient.Client
	tm   *tasks.Manager
}

// NewTasksHandler creates a new TasksHandler.
func NewTasksHandler(gc *grpcclient.Client, tm *tasks.Manager) *TasksHandler {
	return &TasksHandler{grpc: gc, tm: tm}
}

// Routes registers all task-management routes on the given chi router.
func (h *TasksHandler) Routes(r chi.Router) {
	r.Get("/", h.List)
	r.Delete("/", h.ClearFinished)
	r.Get("/{id}", h.Get)
	r.Post("/{id}/cancel", h.Cancel)
	r.Post("/{id}/retry", h.Retry)
}

// List returns all tracked tasks.
func (h *TasksHandler) List(w http.ResponseWriter, r *http.Request) {
	taskList := h.tm.List()
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"tasks": taskList,
		"count": len(taskList),
	})
}

// ClearFinished removes all completed, failed, or cancelled tasks.
func (h *TasksHandler) ClearFinished(w http.ResponseWriter, r *http.Request) {
	cleared := h.tm.ClearFinished()
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"cleared": cleared,
	})
}

// Get returns the status of a single task.
func (h *TasksHandler) Get(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	task := h.tm.Get(id)
	if task == nil {
		writeError(w, http.StatusNotFound, fmt.Sprintf("task %s not found", id))
		return
	}
	writeJSON(w, http.StatusOK, task)
}

// Cancel cancels a running task.
func (h *TasksHandler) Cancel(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if ok := h.tm.Cancel(id); !ok {
		writeError(w, http.StatusNotFound, fmt.Sprintf("task %s not found", id))
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"task_id": id,
		"status":  "cancelled",
	})
}

// Retry re-launches a task using the stored request parameters. Only
// completed, failed, or cancelled tasks can be retried.
func (h *TasksHandler) Retry(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	task := h.tm.Get(id)
	if task == nil {
		writeError(w, http.StatusNotFound, fmt.Sprintf("task %s not found", id))
		return
	}

	// Only terminal tasks can be retried.
	switch task.Status {
	case tasks.StatusCompleted, tasks.StatusFailed, tasks.StatusCancelled:
		// OK
	default:
		writeError(w, http.StatusConflict, fmt.Sprintf("task %s is in state %s, cannot retry", id, task.Status))
		return
	}

	if h.grpc.Indexing == nil {
		writeError(w, http.StatusServiceUnavailable, "indexing service not available")
		return
	}

	// Create a new task with the same parameters.
	newID := h.tm.Create(task.Type, task.RequestParams)
	h.tm.Start(newID)

	ctx, cancel := context.WithCancel(context.Background())
	h.tm.SetCancelFunc(newID, cancel)

	params := task.RequestParams

	switch task.Type {
	case "index_codebase":
		go h.runRetryStream(ctx, newID, func() (grpcclient.IndexingStream, error) {
			return h.grpc.Indexing.IndexCodebase(ctx, &grpcclient.IndexCodebaseRequest{
				RootPath:      stringParam(params, "root_path"),
				Collection:    stringParam(params, "collection"),
				Incremental:   boolParam(params, "incremental"),
				ChunkSize:     int32Param(params, "chunk_size"),
				ChunkOverlap:  int32Param(params, "chunk_overlap"),
				ExtraSkipDirs: stringSliceParam(params, "extra_skip_dirs"),
			})
		})
	case "index_documents":
		go h.runRetryStream(ctx, newID, func() (grpcclient.IndexingStream, error) {
			return h.grpc.Indexing.IndexDocuments(ctx, &grpcclient.IndexDocumentsRequest{
				Paths:        stringSliceParam(params, "paths"),
				Collection:   stringParam(params, "collection"),
				ChunkSize:    int32Param(params, "chunk_size"),
				ChunkOverlap: int32Param(params, "chunk_overlap"),
				SourceTag:    stringParam(params, "source_tag"),
			})
		})
	case "index_images":
		go h.runRetryStream(ctx, newID, func() (grpcclient.IndexingStream, error) {
			return h.grpc.Indexing.IndexImages(ctx, &grpcclient.IndexImagesRequest{
				RootPath:       stringParam(params, "root_path"),
				Collection:     stringParam(params, "collection"),
				VisionModel:    stringParam(params, "vision_model"),
				CaptionPrompt:  stringParam(params, "caption_prompt"),
				Incremental:    boolParam(params, "incremental"),
				MaxImageSizeKb: int32Param(params, "max_image_size_kb"),
				ExtraSkipDirs:  stringSliceParam(params, "extra_skip_dirs"),
			})
		})
	case "index_uploads":
		go h.runRetryStream(ctx, newID, func() (grpcclient.IndexingStream, error) {
			return h.grpc.Indexing.IndexUploads(ctx, &grpcclient.IndexUploadsRequest{
				SavedPaths:    stringSliceParam(params, "saved_paths"),
				Collection:    stringParam(params, "collection"),
				ChunkSize:     int32Param(params, "chunk_size"),
				ChunkOverlap:  int32Param(params, "chunk_overlap"),
				SourceTag:     stringParam(params, "source_tag"),
				VisionModel:   stringParam(params, "vision_model"),
				CaptionPrompt: stringParam(params, "caption_prompt"),
			})
		})
	case "index_smb":
		go h.runRetryStream(ctx, newID, func() (grpcclient.IndexingStream, error) {
			return h.grpc.Indexing.IndexSMBFiles(ctx, &grpcclient.IndexSMBFilesRequest{
				ShareId:      stringParam(params, "share_id"),
				RemotePaths:  stringSliceParam(params, "remote_paths"),
				Collection:   stringParam(params, "collection"),
				ChunkSize:    int32Param(params, "chunk_size"),
				ChunkOverlap: int32Param(params, "chunk_overlap"),
				SourceTag:    stringParam(params, "source_tag"),
				Server:       stringParam(params, "server"),
				Share:        stringParam(params, "share"),
				Username:     stringParam(params, "username"),
				Password:     stringParam(params, "password"),
				Domain:       stringParam(params, "domain"),
				Port:         int32Param(params, "port"),
			})
		})
	default:
		h.tm.Fail(newID, fmt.Sprintf("unknown task type: %s", task.Type))
		writeError(w, http.StatusBadRequest, fmt.Sprintf("cannot retry task type: %s", task.Type))
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]interface{}{
		"task_id":          newID,
		"original_task_id": id,
		"status":           "started",
	})
}

// runRetryStream is the same logic as RAGHandler.runIndexStream but lives on
// TasksHandler for retry access.
func (h *TasksHandler) runRetryStream(ctx context.Context, taskID string, openStream func() (grpcclient.IndexingStream, error)) {
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
		}
	}
}

// --- Param extraction helpers ---

func stringParam(m map[string]interface{}, key string) string {
	v, _ := m[key].(string)
	return v
}

func boolParam(m map[string]interface{}, key string) bool {
	v, _ := m[key].(bool)
	return v
}

func int32Param(m map[string]interface{}, key string) int32 {
	switch v := m[key].(type) {
	case int32:
		return v
	case int:
		return int32(v)
	case float64:
		return int32(v)
	case int64:
		return int32(v)
	default:
		return 0
	}
}

func stringSliceParam(m map[string]interface{}, key string) []string {
	switch v := m[key].(type) {
	case []string:
		return v
	case []interface{}:
		out := make([]string, 0, len(v))
		for _, item := range v {
			if s, ok := item.(string); ok {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}
