package tasks

import (
	"context"
	"sync"
	"time"

	"github.com/google/uuid"
)

// TaskStatus represents the lifecycle state of a background task.
type TaskStatus string

const (
	StatusPending   TaskStatus = "pending"
	StatusRunning   TaskStatus = "running"
	StatusCompleted TaskStatus = "completed"
	StatusFailed    TaskStatus = "failed"
	StatusCancelled TaskStatus = "cancelled"
)

// TaskInfo holds all state for a single background task.
type TaskInfo struct {
	ID            string                 `json:"task_id"`
	Type          string                 `json:"type"`
	Status        TaskStatus             `json:"status"`
	Progress      float64                `json:"progress"`
	Result        map[string]string      `json:"result,omitempty"`
	Error         string                 `json:"error,omitempty"`
	CreatedAt     time.Time              `json:"created_at"`
	StartedAt     *time.Time             `json:"started_at,omitempty"`
	CompletedAt   *time.Time             `json:"completed_at,omitempty"`
	RequestParams map[string]interface{} `json:"request_params,omitempty"`

	cancelFunc context.CancelFunc `json:"-"`
}

// Manager is a thread-safe, in-memory task store that mirrors the Python
// TaskManager. All public methods are safe for concurrent use.
type Manager struct {
	mu    sync.RWMutex
	tasks map[string]*TaskInfo
}

// NewManager creates a new empty task manager.
func NewManager() *Manager {
	return &Manager{
		tasks: make(map[string]*TaskInfo),
	}
}

// Create registers a new task in pending state and returns its generated ID.
func (m *Manager) Create(taskType string, params map[string]interface{}) string {
	id := uuid.New().String()
	m.mu.Lock()
	defer m.mu.Unlock()

	m.tasks[id] = &TaskInfo{
		ID:            id,
		Type:          taskType,
		Status:        StatusPending,
		Progress:      0,
		CreatedAt:     time.Now(),
		RequestParams: params,
	}
	return id
}

// Start transitions a task to the running state and records the start time.
func (m *Manager) Start(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	t, ok := m.tasks[id]
	if !ok {
		return
	}
	t.Status = StatusRunning
	now := time.Now()
	t.StartedAt = &now
}

// UpdateProgress sets the progress percentage (0-100) and optionally the
// status string for a running task.
func (m *Manager) UpdateProgress(id string, progress float64, status string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	t, ok := m.tasks[id]
	if !ok {
		return
	}
	t.Progress = progress
	if status != "" {
		t.Status = TaskStatus(status)
	}
}

// Complete marks a task as completed with the given result map.
func (m *Manager) Complete(id string, result map[string]string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	t, ok := m.tasks[id]
	if !ok {
		return
	}
	t.Status = StatusCompleted
	t.Progress = 100
	t.Result = result
	now := time.Now()
	t.CompletedAt = &now
}

// Fail marks a task as failed with the given error message.
func (m *Manager) Fail(id string, errMsg string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	t, ok := m.tasks[id]
	if !ok {
		return
	}
	t.Status = StatusFailed
	t.Error = errMsg
	now := time.Now()
	t.CompletedAt = &now
}

// Cancel cancels a running task by invoking its cancel function and marking
// the task as cancelled. Returns true if the task was found and cancelled.
func (m *Manager) Cancel(id string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()

	t, ok := m.tasks[id]
	if !ok {
		return false
	}
	if t.cancelFunc != nil {
		t.cancelFunc()
	}
	t.Status = StatusCancelled
	now := time.Now()
	t.CompletedAt = &now
	return true
}

// Get returns a copy of the task info for the given ID, or nil if not found.
func (m *Manager) Get(id string) *TaskInfo {
	m.mu.RLock()
	defer m.mu.RUnlock()

	t, ok := m.tasks[id]
	if !ok {
		return nil
	}
	// Return a shallow copy to avoid races on mutable fields.
	cp := *t
	return &cp
}

// List returns a copy of all tasks, most recent first.
func (m *Manager) List() []*TaskInfo {
	m.mu.RLock()
	defer m.mu.RUnlock()

	out := make([]*TaskInfo, 0, len(m.tasks))
	for _, t := range m.tasks {
		cp := *t
		out = append(out, &cp)
	}
	return out
}

// ClearFinished removes all tasks in a terminal state (completed, failed,
// cancelled). Returns the number of tasks removed.
func (m *Manager) ClearFinished() int {
	m.mu.Lock()
	defer m.mu.Unlock()

	count := 0
	for id, t := range m.tasks {
		switch t.Status {
		case StatusCompleted, StatusFailed, StatusCancelled:
			delete(m.tasks, id)
			count++
		}
	}
	return count
}

// SetCancelFunc attaches a context cancel function to a task so that
// Cancel() can abort the underlying gRPC stream.
func (m *Manager) SetCancelFunc(id string, cancel context.CancelFunc) {
	m.mu.Lock()
	defer m.mu.Unlock()

	t, ok := m.tasks[id]
	if !ok {
		return
	}
	t.cancelFunc = cancel
}
