package proxy

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
)

// NewQdrantProxy creates an HTTP reverse proxy to the Qdrant vector database.
//
// Unlike the Ollama proxy, Qdrant responses are not streamed, so no special
// flush configuration is needed.
func NewQdrantProxy(targetURL string) (*httputil.ReverseProxy, error) {
	target, err := url.Parse(targetURL)
	if err != nil {
		return nil, err
	}

	proxy := httputil.NewSingleHostReverseProxy(target)

	// Replace the default director to strip the /api/qdrant prefix and
	// forward the remaining path to Qdrant.
	originalDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		originalDirector(req)
		// Strip the /api/qdrant prefix so /api/qdrant/collections becomes /collections.
		req.URL.Path = strings.TrimPrefix(req.URL.Path, "/api/qdrant")
		if req.URL.Path == "" {
			req.URL.Path = "/"
		}
		req.URL.RawPath = ""
		req.Host = target.Host
	}

	return proxy, nil
}
