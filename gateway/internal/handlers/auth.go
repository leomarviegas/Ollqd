package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/alfagnish/ollqd-gateway/internal/config"
	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/alfagnish/ollqd-gateway/internal/middleware"
	"github.com/go-chi/chi/v5"
)

// AuthHandler provides login/logout/me endpoints.
type AuthHandler struct {
	cfg  *config.Config
	grpc *grpcclient.Client
}

// NewAuthHandler creates a new AuthHandler.
func NewAuthHandler(cfg *config.Config, gc *grpcclient.Client) *AuthHandler {
	return &AuthHandler{cfg: cfg, grpc: gc}
}

// Routes registers auth routes on the given chi router.
func (h *AuthHandler) Routes(r chi.Router) {
	r.Post("/login", h.Login)
	r.Post("/logout", h.Logout)
	r.With(middleware.RequireAuth(h.cfg.JWTSecret)).Get("/me", h.Me)
}

// Login authenticates a user and sets an HttpOnly cookie.
func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Username string `json:"username"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	resp, err := h.grpc.Auth.Login(r.Context(), &grpcclient.LoginRequest{
		Username: req.Username,
		Password: req.Password,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, fmt.Sprintf("grpc error: %v", err))
		return
	}

	if !resp.Success {
		writeError(w, http.StatusUnauthorized, resp.Error)
		return
	}

	token, err := middleware.GenerateToken(h.cfg.JWTSecret, resp.Username, resp.Role)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to generate token")
		return
	}

	http.SetCookie(w, &http.Cookie{
		Name:     middleware.CookieName,
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   int(middleware.TokenExpiry.Seconds()),
	})

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"token":    token,
		"username": resp.Username,
		"role":     resp.Role,
	})
}

// Logout clears the auth cookie.
func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{
		Name:     middleware.CookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
	})
	writeJSON(w, http.StatusOK, map[string]string{"status": "logged out"})
}

// Me returns the current authenticated user's info.
func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"username": middleware.UsernameFromContext(r.Context()),
		"role":     middleware.RoleFromContext(r.Context()),
	})
}
