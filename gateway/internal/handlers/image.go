package handlers

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/alfagnish/ollqd-gateway/internal/config"
	"github.com/go-chi/chi/v5"
)

// ImageHandler serves static image files from the upload directory. This is
// used by the frontend to display indexed images.
type ImageHandler struct {
	cfg *config.Config
}

// NewImageHandler creates a new ImageHandler.
func NewImageHandler(cfg *config.Config) *ImageHandler {
	return &ImageHandler{cfg: cfg}
}

// Routes registers image-serving routes.
func (h *ImageHandler) Routes(r chi.Router) {
	r.Get("/", h.ServeImage)
}

// ServeImage returns a file from the upload directory based on the `path`
// query parameter. The path is sanitized to prevent directory traversal.
func (h *ImageHandler) ServeImage(w http.ResponseWriter, r *http.Request) {
	relPath := r.URL.Query().Get("path")
	if relPath == "" {
		writeError(w, http.StatusBadRequest, "missing 'path' query parameter")
		return
	}

	// Sanitize: clean the path and ensure it doesn't escape the upload dir.
	cleaned := filepath.Clean(relPath)
	if strings.Contains(cleaned, "..") {
		writeError(w, http.StatusBadRequest, "invalid path")
		return
	}

	fullPath := filepath.Join(h.cfg.UploadDir, cleaned)

	// Verify the resolved path is still under the upload directory.
	absUpload, _ := filepath.Abs(h.cfg.UploadDir)
	absFile, _ := filepath.Abs(fullPath)
	if !strings.HasPrefix(absFile, absUpload) {
		writeError(w, http.StatusForbidden, "access denied")
		return
	}

	// Check the file exists.
	info, err := os.Stat(fullPath)
	if err != nil || info.IsDir() {
		writeError(w, http.StatusNotFound, "file not found")
		return
	}

	http.ServeFile(w, r, fullPath)
}
