package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"

	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/go-chi/chi/v5"
)

// UsersHandler provides user management endpoints (admin only).
type UsersHandler struct {
	grpc *grpcclient.Client
}

// NewUsersHandler creates a new UsersHandler.
func NewUsersHandler(gc *grpcclient.Client) *UsersHandler {
	return &UsersHandler{grpc: gc}
}

// Routes registers user management routes on the given chi router.
func (h *UsersHandler) Routes(r chi.Router) {
	r.Get("/", h.ListUsers)
	r.Post("/", h.CreateUser)
	r.Delete("/{username}", h.DeleteUser)
}

// ListUsers returns all users.
func (h *UsersHandler) ListUsers(w http.ResponseWriter, r *http.Request) {
	resp, err := h.grpc.Auth.ListUsers(r.Context())
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	type userJSON struct {
		Username  string `json:"username"`
		Role      string `json:"role"`
		CreatedAt string `json:"created_at"`
	}
	users := make([]userJSON, 0, len(resp.Users))
	for _, u := range resp.Users {
		users = append(users, userJSON{
			Username:  u.Username,
			Role:      u.Role,
			CreatedAt: u.CreatedAt,
		})
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"users": users})
}

// CreateUser creates a new user.
func (h *UsersHandler) CreateUser(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Username string `json:"username"`
		Password string `json:"password"`
		Role     string `json:"role"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Auth.CreateUser(r.Context(), &grpcclient.CreateUserRequest{
		Username: req.Username,
		Password: req.Password,
		Role:     req.Role,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	writeJSON(w, http.StatusCreated, map[string]interface{}{
		"username":   resp.User.Username,
		"role":       resp.User.Role,
		"created_at": resp.User.CreatedAt,
	})
}

// DeleteUser deletes a user by username.
func (h *UsersHandler) DeleteUser(w http.ResponseWriter, r *http.Request) {
	username := chi.URLParam(r, "username")

	resp, err := h.grpc.Auth.DeleteUser(r.Context(), &grpcclient.DeleteUserRequest{
		Username: username,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	if !resp.Deleted {
		writeError(w, http.StatusConflict, resp.Error)
		return
	}

	writeJSON(w, http.StatusOK, map[string]bool{"deleted": true})
}
