package handlers

import (
	"context"
	"encoding/json"
	"io"
	"log"
	"net/http"

	grpcclient "github.com/alfagnish/ollqd-gateway/internal/grpc"
	"github.com/go-chi/chi/v5"
	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 4096,
	// Allow all origins (CORS is handled at the middleware level).
	CheckOrigin: func(r *http.Request) bool { return true },
}

// WSHandler bridges WebSocket connections to the gRPC ChatService stream.
type WSHandler struct {
	grpc *grpcclient.Client
}

// NewWSHandler creates a new WSHandler.
func NewWSHandler(gc *grpcclient.Client) *WSHandler {
	return &WSHandler{grpc: gc}
}

// Routes registers the WebSocket endpoint.
func (h *WSHandler) Routes(r chi.Router) {
	r.Get("/", h.HandleWS)
}

// wsMessage is the JSON structure expected from WebSocket clients.
type wsMessage struct {
	Message    string `json:"message"`
	Collection string `json:"collection"`
	Model      string `json:"model"`
	PIIEnabled bool   `json:"pii_enabled"`
}

// wsEvent is the JSON structure sent back to WebSocket clients, mirroring
// ChatEvent from the gRPC service.
type wsEvent struct {
	Type             string              `json:"type"`
	Content          string              `json:"content,omitempty"`
	Sources          []grpcclient.SearchHit `json:"sources,omitempty"`
	PIIMasked        bool                `json:"pii_masked,omitempty"`
	PIIEntitiesCount int32               `json:"pii_entities_count,omitempty"`
}

// HandleWS upgrades the HTTP connection to a WebSocket, then enters a
// read loop. For each message received it opens a gRPC Chat stream and
// pipes ChatEvent frames back as JSON over the WebSocket. When the
// WebSocket disconnects the active gRPC context is cancelled.
func (h *WSHandler) HandleWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("websocket upgrade error: %v", err)
		return
	}
	defer conn.Close()

	for {
		// Read next message from the client.
		_, raw, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				log.Printf("websocket read error: %v", err)
			}
			return
		}

		var msg wsMessage
		if err := json.Unmarshal(raw, &msg); err != nil {
			h.writeWSError(conn, "invalid JSON message")
			continue
		}

		if h.grpc.Chat == nil {
			h.writeWSError(conn, "chat service not available")
			continue
		}

		// Create a cancellable context for this chat exchange. If the
		// WebSocket closes while streaming, the gRPC call is cancelled.
		ctx, cancel := context.WithCancel(r.Context())

		stream, err := h.grpc.Chat.Chat(ctx, &grpcclient.ChatRequest{
			Message:    msg.Message,
			Collection: msg.Collection,
			Model:      msg.Model,
			PiiEnabled: msg.PIIEnabled,
		})
		if err != nil {
			cancel()
			h.writeWSError(conn, "failed to start chat: "+err.Error())
			continue
		}

		// Stream gRPC events to the WebSocket.
		h.streamToWS(conn, stream)

		stream.Close()
		cancel()
	}
}

// streamToWS reads from the gRPC stream and writes each event as a JSON
// frame on the WebSocket.
func (h *WSHandler) streamToWS(conn *websocket.Conn, stream grpcclient.ChatStream) {
	for {
		event, err := stream.Recv()
		if err == io.EOF {
			return
		}
		if err != nil {
			h.writeWSError(conn, "stream error: "+err.Error())
			return
		}

		wsEvt := wsEvent{
			Type:             event.Type,
			Content:          event.Content,
			PIIMasked:        event.PiiMasked,
			PIIEntitiesCount: event.PiiEntitiesCount,
		}
		if len(event.Sources) > 0 {
			wsEvt.Sources = make([]grpcclient.SearchHit, len(event.Sources))
			for i, s := range event.Sources {
				wsEvt.Sources[i] = *s
			}
		}

		data, _ := json.Marshal(wsEvt)
		if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
			log.Printf("websocket write error: %v", err)
			return
		}
	}
}

func (h *WSHandler) writeWSError(conn *websocket.Conn, msg string) {
	data, _ := json.Marshal(wsEvent{
		Type:    "error",
		Content: msg,
	})
	conn.WriteMessage(websocket.TextMessage, data)
}
