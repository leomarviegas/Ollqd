// Package main demonstrates a simple Go HTTP server for testing.
// Known symbols: ServeHTTP, healthHandler, UserStore, GetUser
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
)

// User represents a user entity for the application.
type User struct {
	ID    int    `json:"id"`
	Name  string `json:"name"`
	Email string `json:"email"`
}

// UserStore is an in-memory store for users.
type UserStore struct {
	mu    sync.RWMutex
	users map[int]*User
}

// NewUserStore creates an empty UserStore.
func NewUserStore() *UserStore {
	return &UserStore{users: make(map[int]*User)}
}

// GetUser retrieves a user by ID, returns nil if not found.
func (s *UserStore) GetUser(id int) *User {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.users[id]
}

// AddUser adds a user to the store.
func (s *UserStore) AddUser(u *User) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.users[u.ID] = u
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func main() {
	store := NewUserStore()
	store.AddUser(&User{ID: 1, Name: "Alice", Email: "alice@example.com"})

	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/users", func(w http.ResponseWriter, r *http.Request) {
		u := store.GetUser(1)
		if u == nil {
			http.Error(w, "not found", 404)
			return
		}
		json.NewEncoder(w).Encode(u)
	})

	fmt.Println("Listening on :9090")
	http.ListenAndServe(":9090", nil)
}
