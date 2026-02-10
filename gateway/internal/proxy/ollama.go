package proxy

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"
)

// NewOllamaProxy creates an HTTP reverse proxy to the Ollama API.
//
// It supports streaming responses (chunked transfer encoding) for
// endpoints like /api/chat, /api/generate, and /api/pull by setting
// FlushInterval to -1, which causes the proxy to flush every write
// to the client immediately.
func NewOllamaProxy(targetURL string) (*httputil.ReverseProxy, error) {
	target, err := url.Parse(targetURL)
	if err != nil {
		return nil, err
	}

	proxy := httputil.NewSingleHostReverseProxy(target)

	// Replace the default director to strip the /api/ollama prefix and
	// forward the remaining path to Ollama.
	originalDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		originalDirector(req)
		// Strip the /api/ollama prefix so /api/ollama/api/tags becomes /api/tags.
		req.URL.Path = strings.TrimPrefix(req.URL.Path, "/api/ollama")
		if req.URL.Path == "" {
			req.URL.Path = "/"
		}
		req.URL.RawPath = ""
		req.Host = target.Host
	}

	// Enable streaming: flush every chunk immediately.
	proxy.FlushInterval = -1 * time.Millisecond

	// Increase default transport timeouts for long-running model operations.
	proxy.Transport = &http.Transport{
		MaxIdleConns:        100,
		IdleConnTimeout:     90 * time.Second,
		TLSHandshakeTimeout: 10 * time.Second,
		// ResponseHeaderTimeout is intentionally 0 (no timeout) to support
		// long-running streaming responses from Ollama.
	}

	return proxy, nil
}
