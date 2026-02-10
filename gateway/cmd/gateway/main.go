package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/alfagnish/ollqd-gateway/internal/config"
	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/alfagnish/ollqd-gateway/internal/server"
	"github.com/alfagnish/ollqd-gateway/internal/tasks"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)

	// 1. Load configuration from environment variables.
	cfg := config.Load()
	log.Printf("config: listen=%s worker=%s ollama=%s qdrant=%s",
		cfg.ListenAddr, cfg.WorkerAddr, cfg.OllamaURL, cfg.QdrantURL)

	// 2. Connect to the Python gRPC worker.
	log.Printf("connecting to gRPC worker at %s ...", cfg.WorkerAddr)
	gc, err := grpcclient.NewClient(cfg.WorkerAddr)
	if err != nil {
		// Non-fatal: the gateway can still serve health checks, proxies,
		// and static files without the gRPC worker. Handlers will return
		// 503 for gRPC-dependent endpoints.
		log.Printf("WARNING: gRPC worker unavailable: %v", err)
		gc = &grpcclient.Client{} // empty client with nil stubs
	} else {
		defer gc.Close()
		log.Println("gRPC worker connected")
	}

	// 3. Create the in-memory task manager.
	tm := tasks.NewManager()

	// 4. Set up the chi router with all handlers.
	handler, err := server.New(cfg, gc, tm)
	if err != nil {
		log.Fatalf("failed to create server: %v", err)
	}

	// 5. Start the HTTP server.
	srv := &http.Server{
		Addr:         cfg.ListenAddr,
		Handler:      handler,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 0, // no write timeout to support streaming responses
		IdleTimeout:  120 * time.Second,
	}

	// Graceful shutdown on SIGINT / SIGTERM.
	done := make(chan os.Signal, 1)
	signal.Notify(done, os.Interrupt, syscall.SIGTERM)

	go func() {
		log.Printf("gateway listening on %s", cfg.ListenAddr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	<-done
	log.Println("shutting down...")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("graceful shutdown error: %v", err)
	}

	log.Println("gateway stopped")
}
