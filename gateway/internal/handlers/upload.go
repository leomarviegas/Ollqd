package handlers

import (
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/alfagnish/ollqd-gateway/internal/config"
	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/alfagnish/ollqd-gateway/internal/tasks"
	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// allowedExtensions is the set of file extensions accepted for upload.
var allowedExtensions = map[string]bool{
	".txt":  true,
	".md":   true,
	".py":   true,
	".js":   true,
	".ts":   true,
	".go":   true,
	".rs":   true,
	".java": true,
	".c":    true,
	".cpp":  true,
	".h":    true,
	".hpp":  true,
	".rb":   true,
	".php":  true,
	".sh":   true,
	".yaml": true,
	".yml":  true,
	".json": true,
	".toml": true,
	".xml":  true,
	".html": true,
	".css":  true,
	".sql":  true,
	".r":    true,
	".pdf":  true,
	".docx": true,
	".pptx": true,
	".xlsx": true,
	".odt":  true,
	".rtf":  true,
	".csv":  true,
	".png":  true,
	".jpg":  true,
	".jpeg": true,
	".gif":  true,
	".webp": true,
	".svg":  true,
	".bmp":  true,
	".tiff": true,
}

// UploadHandler handles multipart file uploads and triggers background
// indexing of the uploaded files.
type UploadHandler struct {
	cfg  *config.Config
	grpc *grpcclient.Client
	tm   *tasks.Manager
}

// NewUploadHandler creates a new UploadHandler.
func NewUploadHandler(cfg *config.Config, gc *grpcclient.Client, tm *tasks.Manager) *UploadHandler {
	return &UploadHandler{cfg: cfg, grpc: gc, tm: tm}
}

// Routes registers upload routes.
func (h *UploadHandler) Routes(r chi.Router) {
	r.Post("/", h.Upload)
}

// Upload parses the multipart form, validates file extensions and sizes,
// saves files to UPLOAD_DIR, and starts a background gRPC IndexUploads stream.
func (h *UploadHandler) Upload(w http.ResponseWriter, r *http.Request) {
	maxBytes := h.cfg.MaxUploadSizeMB << 20 // convert MB to bytes
	r.Body = http.MaxBytesReader(w, r.Body, maxBytes)

	if err := r.ParseMultipartForm(maxBytes); err != nil {
		writeError(w, http.StatusRequestEntityTooLarge,
			fmt.Sprintf("upload exceeds maximum size of %d MB", h.cfg.MaxUploadSizeMB))
		return
	}

	// Read optional form fields.
	collection := r.FormValue("collection")
	sourceTag := r.FormValue("source_tag")
	visionModel := r.FormValue("vision_model")
	captionPrompt := r.FormValue("caption_prompt")

	files := r.MultipartForm.File["files"]
	if len(files) == 0 {
		writeError(w, http.StatusBadRequest, "no files provided in 'files' field")
		return
	}

	// Ensure upload directory exists.
	if err := os.MkdirAll(h.cfg.UploadDir, 0o755); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to create upload directory")
		return
	}

	var savedPaths []string
	var savedNames []string

	for _, fh := range files {
		ext := strings.ToLower(filepath.Ext(fh.Filename))
		if !allowedExtensions[ext] {
			writeError(w, http.StatusBadRequest,
				fmt.Sprintf("file extension %s is not allowed", ext))
			return
		}

		// Generate a unique filename to prevent collisions.
		destName := uuid.New().String() + ext
		destPath := filepath.Join(h.cfg.UploadDir, destName)

		src, err := fh.Open()
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to read uploaded file")
			return
		}

		dst, err := os.Create(destPath)
		if err != nil {
			src.Close()
			writeError(w, http.StatusInternalServerError, "failed to save uploaded file")
			return
		}

		if _, err := io.Copy(dst, src); err != nil {
			src.Close()
			dst.Close()
			writeError(w, http.StatusInternalServerError, "failed to write uploaded file")
			return
		}

		src.Close()
		dst.Close()

		savedPaths = append(savedPaths, destPath)
		savedNames = append(savedNames, fh.Filename)
	}

	// If no gRPC indexing service, just report saved files.
	if h.grpc.Indexing == nil {
		writeJSON(w, http.StatusOK, map[string]interface{}{
			"saved":   savedNames,
			"count":   len(savedPaths),
			"message": "files saved but indexing service unavailable",
		})
		return
	}

	// Create a background indexing task.
	params := map[string]interface{}{
		"saved_paths":    savedPaths,
		"collection":     collection,
		"source_tag":     sourceTag,
		"vision_model":   visionModel,
		"caption_prompt": captionPrompt,
	}

	taskID := h.tm.Create("index_uploads", params)
	h.tm.Start(taskID)

	ctx, cancel := context.WithCancel(context.Background())
	h.tm.SetCancelFunc(taskID, cancel)

	go func() {
		stream, err := h.grpc.Indexing.IndexUploads(ctx, &grpcclient.IndexUploadsRequest{
			SavedPaths:    savedPaths,
			Collection:    collection,
			SourceTag:     sourceTag,
			VisionModel:   visionModel,
			CaptionPrompt: captionPrompt,
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
				log.Printf("[upload task %s] unknown status: %s", taskID, progress.Status)
			}
		}
	}()

	writeJSON(w, http.StatusAccepted, map[string]interface{}{
		"task_id": taskID,
		"status":  "started",
		"files":   savedNames,
		"count":   len(savedPaths),
	})
}
