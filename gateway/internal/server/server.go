package server

import (
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/alfagnish/ollqd-gateway/internal/config"
	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/alfagnish/ollqd-gateway/internal/handlers"
	"github.com/alfagnish/ollqd-gateway/internal/proxy"
	"github.com/alfagnish/ollqd-gateway/internal/tasks"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
)

// New creates a fully-configured chi router with all route groups,
// middleware, and handlers wired together.
func New(cfg *config.Config, gc *grpcclient.Client, tm *tasks.Manager) (http.Handler, error) {
	r := chi.NewRouter()

	// ── Middleware ───────────────────────────────────────────
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"},
		AllowedHeaders:   []string{"*"},
		AllowCredentials: true,
		MaxAge:           300,
	}))
	r.Use(requestLogger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.RealIP)

	// ── Reverse proxies ─────────────────────────────────────
	ollamaProxy, err := proxy.NewOllamaProxy(cfg.OllamaURL)
	if err != nil {
		return nil, err
	}

	qdrantProxy, err := proxy.NewQdrantProxy(cfg.QdrantURL)
	if err != nil {
		return nil, err
	}

	// ── Handlers ────────────────────────────────────────────
	systemH := handlers.NewSystemHandler(cfg, gc)
	ollamaH := handlers.NewOllamaHandler(ollamaProxy)
	qdrantH := handlers.NewQdrantHandler(qdrantProxy)
	ragH := handlers.NewRAGHandler(gc, tm)
	tasksH := handlers.NewTasksHandler(gc, tm)
	uploadH := handlers.NewUploadHandler(cfg, gc, tm)
	wsH := handlers.NewWSHandler(gc)
	smbH := handlers.NewSMBHandler(gc, tm)
	imageH := handlers.NewImageHandler(cfg)

	// ── Route groups ────────────────────────────────────────
	r.Route("/api/system", systemH.Routes)
	r.Route("/api/ollama", ollamaH.Routes)
	r.Route("/api/qdrant", qdrantH.Routes)

	r.Route("/api/rag", func(r chi.Router) {
		ragH.Routes(r)
		r.Route("/tasks", tasksH.Routes)
		r.Route("/upload", uploadH.Routes)
		r.Route("/ws", wsH.Routes)
		r.Route("/image", imageH.Routes)
	})

	r.Route("/api/smb", smbH.Routes)

	return r, nil
}

// requestLogger is a simple middleware that logs each HTTP request with
// method, path, status code, and duration.
func requestLogger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ww := middleware.NewWrapResponseWriter(w, r.ProtoMajor)

		next.ServeHTTP(ww, r)

		// Only log API requests to reduce noise from static file serving.
		if strings.HasPrefix(r.URL.Path, "/api/") {
			duration := time.Since(start)
			status := ww.Status()
			if status == 0 {
				status = 200
			}
			log.Printf("%s %s %d %s",
				r.Method,
				r.URL.Path,
				status,
				duration.Round(time.Millisecond),
			)
		}
	})
}
