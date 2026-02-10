package docker

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"
)

// Manager provides a thin Docker Engine API client over a Unix socket.
type Manager struct {
	client *http.Client
}

// New creates a Manager that talks to Docker via the given Unix socket path.
func New(socketPath string) *Manager {
	return &Manager{
		client: &http.Client{
			Transport: &http.Transport{
				DialContext: func(_ context.Context, _, _ string) (net.Conn, error) {
					return net.DialTimeout("unix", socketPath, 5*time.Second)
				},
			},
			Timeout: 60 * time.Second,
		},
	}
}

// ContainerStatus returns the status of the named container.
// Possible values: "running", "created", "exited", "paused", "restarting", "not_found".
func (m *Manager) ContainerStatus(ctx context.Context, name string) (string, error) {
	id, err := m.findContainer(ctx, name)
	if err != nil {
		return "", err
	}
	if id == "" {
		return "not_found", nil
	}

	resp, err := m.doRequest(ctx, "GET", fmt.Sprintf("/containers/%s/json", id), nil)
	if err != nil {
		return "", fmt.Errorf("inspect container: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return "not_found", nil
	}
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("inspect: unexpected status %d", resp.StatusCode)
	}

	var info struct {
		State struct {
			Status string `json:"Status"`
		} `json:"State"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&info); err != nil {
		return "", fmt.Errorf("decode inspect: %w", err)
	}

	return info.State.Status, nil
}

// StartContainer starts a stopped or created container.
func (m *Manager) StartContainer(ctx context.Context, name string) error {
	id, err := m.findContainer(ctx, name)
	if err != nil {
		return err
	}
	if id == "" {
		return fmt.Errorf("container %q not found", name)
	}

	resp, err := m.doRequest(ctx, "POST", fmt.Sprintf("/containers/%s/start", id), nil)
	if err != nil {
		return fmt.Errorf("start container: %w", err)
	}
	defer resp.Body.Close()
	io.ReadAll(resp.Body)

	// 204 = started, 304 = already running
	if resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusNotModified {
		return fmt.Errorf("start: unexpected status %d", resp.StatusCode)
	}
	return nil
}

// StopContainer stops a running container with a 10s timeout.
func (m *Manager) StopContainer(ctx context.Context, name string) error {
	id, err := m.findContainer(ctx, name)
	if err != nil {
		return err
	}
	if id == "" {
		return nil // not found = already stopped
	}

	resp, err := m.doRequest(ctx, "POST", fmt.Sprintf("/containers/%s/stop?t=10", id), nil)
	if err != nil {
		return fmt.Errorf("stop container: %w", err)
	}
	defer resp.Body.Close()
	io.ReadAll(resp.Body)

	// 204 = stopped, 304 = already stopped
	if resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusNotModified {
		return fmt.Errorf("stop: unexpected status %d", resp.StatusCode)
	}
	return nil
}

// EnsureContainer guarantees the container exists: pulls the image and creates
// the container if it doesn't exist yet. Does NOT start it.
func (m *Manager) EnsureContainer(ctx context.Context, name string) error {
	id, err := m.findContainer(ctx, name)
	if err != nil {
		return err
	}
	if id != "" {
		return nil // already exists
	}

	// Pull image
	if err := m.pullImage(ctx, "ollama/ollama", "latest"); err != nil {
		return fmt.Errorf("pull image: %w", err)
	}

	// Create container
	spec := map[string]interface{}{
		"Image": "ollama/ollama:latest",
		"Env":   []string{"OLLAMA_KEEP_ALIVE=24h"},
		"ExposedPorts": map[string]interface{}{
			"11434/tcp": struct{}{},
		},
		"HostConfig": map[string]interface{}{
			"PortBindings": map[string]interface{}{
				"11434/tcp": []map[string]string{
					{"HostIp": "", "HostPort": "11434"},
				},
			},
			"Binds": []string{
				"ollqd_ollama_data:/root/.ollama",
			},
			"RestartPolicy": map[string]string{
				"Name": "unless-stopped",
			},
		},
		"NetworkingConfig": map[string]interface{}{
			"EndpointsConfig": map[string]interface{}{
				"ollqd_default": map[string]interface{}{},
			},
		},
	}

	body, err := json.Marshal(spec)
	if err != nil {
		return fmt.Errorf("marshal spec: %w", err)
	}

	resp, err := m.doRequest(ctx, "POST",
		fmt.Sprintf("/containers/create?name=%s", name),
		strings.NewReader(string(body)))
	if err != nil {
		return fmt.Errorf("create container: %w", err)
	}
	defer resp.Body.Close()
	io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusCreated {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("create: status %d: %s", resp.StatusCode, string(respBody))
	}
	return nil
}

// findContainer searches for a container by name and returns its ID, or "" if not found.
func (m *Manager) findContainer(ctx context.Context, name string) (string, error) {
	filter := fmt.Sprintf(`{"name":["%s"]}`, name)
	resp, err := m.doRequest(ctx, "GET",
		fmt.Sprintf("/containers/json?all=true&filters=%s", filter), nil)
	if err != nil {
		return "", fmt.Errorf("list containers: %w", err)
	}
	defer resp.Body.Close()

	var containers []struct {
		ID    string   `json:"Id"`
		Names []string `json:"Names"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&containers); err != nil {
		return "", fmt.Errorf("decode containers: %w", err)
	}

	// Docker prefixes names with "/"
	target := "/" + name
	for _, c := range containers {
		for _, n := range c.Names {
			if n == target {
				return c.ID, nil
			}
		}
	}
	return "", nil
}

// pullImage pulls an image from the registry.
func (m *Manager) pullImage(ctx context.Context, image, tag string) error {
	resp, err := m.doRequest(ctx, "POST",
		fmt.Sprintf("/images/create?fromImage=%s&tag=%s", image, tag), nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	// Drain the stream (Docker sends progress JSON lines)
	io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("pull: unexpected status %d", resp.StatusCode)
	}
	return nil
}

// doRequest sends an HTTP request to the Docker daemon via Unix socket.
func (m *Manager) doRequest(ctx context.Context, method, path string, body io.Reader) (*http.Response, error) {
	url := "http://docker" + path
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return nil, err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	return m.client.Do(req)
}
