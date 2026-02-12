package grpc

import (
	"context"
	"fmt"
	"io"

	pb "github.com/alfagnish/ollqd-gateway/gen/ollqd/v1"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// ──────────────────────────────────────────────────────────────
// Type aliases for generated proto message types.
//
// These allow handler code to continue using grpcclient.SearchHit,
// grpcclient.TaskProgress, etc. without any changes.
// ──────────────────────────────────────────────────────────────

// --- Common / shared types ---

type SearchHit = pb.SearchHit
type TaskProgress = pb.TaskProgress
type ChatEvent = pb.ChatEvent
type Chunk = pb.Chunk

// --- Indexing request types ---

type IndexCodebaseRequest = pb.IndexCodebaseRequest
type IndexDocumentsRequest = pb.IndexDocumentsRequest
type IndexImagesRequest = pb.IndexImagesRequest
type IndexUploadsRequest = pb.IndexUploadsRequest
type IndexSMBFilesRequest = pb.IndexSMBFilesRequest
type CancelTaskRequest = pb.CancelTaskRequest
type CancelTaskResponse = pb.CancelTaskResponse

// --- Search types ---

type SearchRequest = pb.SearchRequest
type SearchCollectionRequest = pb.SearchCollectionRequest
type SearchResponse = pb.SearchResponse

// --- Chat types ---

type ChatRequest = pb.ChatRequest

// --- Embedding types ---

type GetEmbeddingInfoRequest = pb.GetEmbeddingInfoRequest
type EmbeddingInfoResponse = pb.EmbeddingInfoResponse
type TestEmbedRequest = pb.TestEmbedRequest
type TestEmbedResponse = pb.TestEmbedResponse
type CompareModelsRequest = pb.CompareModelsRequest
type ModelTestResult = pb.ModelTestResult
type CompareModelsResponse = pb.CompareModelsResponse
type SetEmbedModelRequest = pb.SetEmbedModelRequest

// --- PII types ---

type TestMaskingRequest = pb.TestMaskingRequest
type PIIEntity = pb.PIIEntity
type TestMaskingResponse = pb.TestMaskingResponse

// --- Config types ---

type GetConfigRequest = pb.GetConfigRequest
type AppConfig = pb.AppConfig
type OllamaConfig = pb.OllamaConfig
type QdrantConfig = pb.QdrantConfig
type ChunkingConfig = pb.ChunkingConfig
type ImageConfig = pb.ImageConfig
type UploadConfig = pb.UploadConfig
type PIIConfig = pb.PIIConfig
type DoclingConfig = pb.DoclingConfig
type UpdateMountedPathsRequest = pb.UpdateMountedPathsRequest
type UpdateMountedPathsResponse = pb.UpdateMountedPathsResponse
type UpdatePIIRequest = pb.UpdatePIIRequest
type PIIConfigResponse = pb.PIIConfigResponse
type UpdateDoclingRequest = pb.UpdateDoclingRequest
type DoclingConfigResponse = pb.DoclingConfigResponse
type UpdateDistanceRequest = pb.UpdateDistanceRequest
type UpdateDistanceResponse = pb.UpdateDistanceResponse
type GetPIIConfigRequest = pb.GetPIIConfigRequest
type GetDoclingConfigRequest = pb.GetDoclingConfigRequest
type UpdateOllamaRequest = pb.UpdateOllamaRequest
type OllamaConfigResponse = pb.OllamaConfigResponse
type UpdateQdrantRequest = pb.UpdateQdrantRequest
type QdrantConfigResponse = pb.QdrantConfigResponse
type UpdateChunkingRequest = pb.UpdateChunkingRequest
type ChunkingConfigResponse = pb.ChunkingConfigResponse
type UpdateImageRequest = pb.UpdateImageRequest
type ImageConfigResponse = pb.ImageConfigResponse
type ResetConfigRequest = pb.ResetConfigRequest
type ResetConfigResponse = pb.ResetConfigResponse

// --- Visualization types ---

type OverviewRequest = pb.OverviewRequest
type VisNode = pb.VisNode
type VisEdge = pb.VisEdge
type OverviewStats = pb.OverviewStats
type OverviewResponse = pb.OverviewResponse
type FileTreeRequest = pb.FileTreeRequest
type FileTreeResponse = pb.FileTreeResponse
type VectorsRequest = pb.VectorsRequest
type VectorPoint = pb.VectorPoint
type VectorsResponse = pb.VectorsResponse

// --- SMB types ---

type SMBTestRequest = pb.SMBTestRequest
type SMBTestResponse = pb.SMBTestResponse
type SMBBrowseRequest = pb.SMBBrowseRequest
type SMBFileEntry = pb.SMBFileEntry
type SMBBrowseResponse = pb.SMBBrowseResponse

// --- Auth types ---

type User = pb.User
type LoginRequest = pb.LoginRequest
type LoginResponse = pb.LoginResponse
type ValidateTokenRequest = pb.ValidateTokenRequest
type ValidateTokenResponse = pb.ValidateTokenResponse
type ListUsersRequest = pb.ListUsersRequest
type ListUsersResponse = pb.ListUsersResponse
type CreateUserRequest = pb.CreateUserRequest
type CreateUserResponse = pb.CreateUserResponse
type DeleteUserRequest = pb.DeleteUserRequest
type DeleteUserResponse = pb.DeleteUserResponse

// ──────────────────────────────────────────────────────────────
// Stream interfaces.
//
// Handlers expect Recv() + io.Closer. The generated gRPC stream
// types provide Recv() and CloseSend() but not Close(). We adapt
// them below with thin wrapper structs.
// ──────────────────────────────────────────────────────────────

// IndexingStream is returned by streaming indexing RPCs.
type IndexingStream interface {
	Recv() (*TaskProgress, error)
	io.Closer
}

// ChatStream is returned by the Chat RPC.
type ChatStream interface {
	Recv() (*ChatEvent, error)
	io.Closer
}

// taskProgressStreamAdapter wraps grpc.ServerStreamingClient[TaskProgress]
// and implements IndexingStream (Recv + io.Closer).
type taskProgressStreamAdapter struct {
	stream grpc.ServerStreamingClient[TaskProgress]
}

func (a *taskProgressStreamAdapter) Recv() (*TaskProgress, error) {
	return a.stream.Recv()
}

func (a *taskProgressStreamAdapter) Close() error {
	return a.stream.CloseSend()
}

// chatEventStreamAdapter wraps grpc.ServerStreamingClient[ChatEvent]
// and implements ChatStream (Recv + io.Closer).
type chatEventStreamAdapter struct {
	stream grpc.ServerStreamingClient[ChatEvent]
}

func (a *chatEventStreamAdapter) Recv() (*ChatEvent, error) {
	return a.stream.Recv()
}

func (a *chatEventStreamAdapter) Close() error {
	return a.stream.CloseSend()
}

// ──────────────────────────────────────────────────────────────
// Service client interfaces.
//
// These match the signatures handlers expect: no ...grpc.CallOption
// variadic parameters.
// ──────────────────────────────────────────────────────────────

// IndexingServiceClient defines the IndexingService RPC methods.
type IndexingServiceClient interface {
	IndexCodebase(ctx context.Context, req *IndexCodebaseRequest) (IndexingStream, error)
	IndexDocuments(ctx context.Context, req *IndexDocumentsRequest) (IndexingStream, error)
	IndexImages(ctx context.Context, req *IndexImagesRequest) (IndexingStream, error)
	IndexUploads(ctx context.Context, req *IndexUploadsRequest) (IndexingStream, error)
	IndexSMBFiles(ctx context.Context, req *IndexSMBFilesRequest) (IndexingStream, error)
	CancelTask(ctx context.Context, req *CancelTaskRequest) (*CancelTaskResponse, error)
}

// SearchServiceClient defines the SearchService RPC methods.
type SearchServiceClient interface {
	Search(ctx context.Context, req *SearchRequest) (*SearchResponse, error)
	SearchCollection(ctx context.Context, req *SearchCollectionRequest) (*SearchResponse, error)
}

// ChatServiceClient defines the ChatService RPC methods.
type ChatServiceClient interface {
	Chat(ctx context.Context, req *ChatRequest) (ChatStream, error)
}

// EmbeddingServiceClient defines the EmbeddingService RPC methods.
type EmbeddingServiceClient interface {
	GetInfo(ctx context.Context) (*EmbeddingInfoResponse, error)
	TestEmbed(ctx context.Context, req *TestEmbedRequest) (*TestEmbedResponse, error)
	CompareModels(ctx context.Context, req *CompareModelsRequest) (*CompareModelsResponse, error)
	SetModel(ctx context.Context, req *SetEmbedModelRequest) (*EmbeddingInfoResponse, error)
}

// PIIServiceClient defines the PIIService RPC methods.
type PIIServiceClient interface {
	TestMasking(ctx context.Context, req *TestMaskingRequest) (*TestMaskingResponse, error)
}

// ConfigServiceClient defines the ConfigService RPC methods.
type ConfigServiceClient interface {
	GetConfig(ctx context.Context) (*AppConfig, error)
	UpdateMountedPaths(ctx context.Context, req *UpdateMountedPathsRequest) (*UpdateMountedPathsResponse, error)
	UpdatePII(ctx context.Context, req *UpdatePIIRequest) (*PIIConfigResponse, error)
	UpdateDocling(ctx context.Context, req *UpdateDoclingRequest) (*DoclingConfigResponse, error)
	UpdateDistance(ctx context.Context, req *UpdateDistanceRequest) (*UpdateDistanceResponse, error)
	UpdateOllama(ctx context.Context, req *UpdateOllamaRequest) (*OllamaConfigResponse, error)
	UpdateQdrant(ctx context.Context, req *UpdateQdrantRequest) (*QdrantConfigResponse, error)
	UpdateChunking(ctx context.Context, req *UpdateChunkingRequest) (*ChunkingConfigResponse, error)
	UpdateImage(ctx context.Context, req *UpdateImageRequest) (*ImageConfigResponse, error)
	GetPIIConfig(ctx context.Context) (*PIIConfigResponse, error)
	GetDoclingConfig(ctx context.Context) (*DoclingConfigResponse, error)
	ResetConfig(ctx context.Context, req *ResetConfigRequest) (*ResetConfigResponse, error)
}

// VisualizationServiceClient defines the VisualizationService RPC methods.
type VisualizationServiceClient interface {
	Overview(ctx context.Context, req *OverviewRequest) (*OverviewResponse, error)
	FileTree(ctx context.Context, req *FileTreeRequest) (*FileTreeResponse, error)
	Vectors(ctx context.Context, req *VectorsRequest) (*VectorsResponse, error)
}

// SMBServiceClient defines the SMBService RPC methods.
type SMBServiceClient interface {
	TestConnection(ctx context.Context, req *SMBTestRequest) (*SMBTestResponse, error)
	Browse(ctx context.Context, req *SMBBrowseRequest) (*SMBBrowseResponse, error)
}

// AuthServiceClient defines the AuthService RPC methods.
type AuthServiceClient interface {
	Login(ctx context.Context, req *LoginRequest) (*LoginResponse, error)
	ListUsers(ctx context.Context) (*ListUsersResponse, error)
	CreateUser(ctx context.Context, req *CreateUserRequest) (*CreateUserResponse, error)
	DeleteUser(ctx context.Context, req *DeleteUserRequest) (*DeleteUserResponse, error)
}

// ──────────────────────────────────────────────────────────────
// Service client adapter structs.
//
// Each adapter wraps the generated gRPC client and drops the
// ...grpc.CallOption parameters so the handler interfaces are
// satisfied.
// ──────────────────────────────────────────────────────────────

// --- indexingAdapter ---

type indexingAdapter struct {
	inner pb.IndexingServiceClient
}

func (a *indexingAdapter) IndexCodebase(ctx context.Context, req *IndexCodebaseRequest) (IndexingStream, error) {
	stream, err := a.inner.IndexCodebase(ctx, req)
	if err != nil {
		return nil, err
	}
	return &taskProgressStreamAdapter{stream: stream}, nil
}

func (a *indexingAdapter) IndexDocuments(ctx context.Context, req *IndexDocumentsRequest) (IndexingStream, error) {
	stream, err := a.inner.IndexDocuments(ctx, req)
	if err != nil {
		return nil, err
	}
	return &taskProgressStreamAdapter{stream: stream}, nil
}

func (a *indexingAdapter) IndexImages(ctx context.Context, req *IndexImagesRequest) (IndexingStream, error) {
	stream, err := a.inner.IndexImages(ctx, req)
	if err != nil {
		return nil, err
	}
	return &taskProgressStreamAdapter{stream: stream}, nil
}

func (a *indexingAdapter) IndexUploads(ctx context.Context, req *IndexUploadsRequest) (IndexingStream, error) {
	stream, err := a.inner.IndexUploads(ctx, req)
	if err != nil {
		return nil, err
	}
	return &taskProgressStreamAdapter{stream: stream}, nil
}

func (a *indexingAdapter) IndexSMBFiles(ctx context.Context, req *IndexSMBFilesRequest) (IndexingStream, error) {
	stream, err := a.inner.IndexSMBFiles(ctx, req)
	if err != nil {
		return nil, err
	}
	return &taskProgressStreamAdapter{stream: stream}, nil
}

func (a *indexingAdapter) CancelTask(ctx context.Context, req *CancelTaskRequest) (*CancelTaskResponse, error) {
	return a.inner.CancelTask(ctx, req)
}

// --- searchAdapter ---

type searchAdapter struct {
	inner pb.SearchServiceClient
}

func (a *searchAdapter) Search(ctx context.Context, req *SearchRequest) (*SearchResponse, error) {
	return a.inner.Search(ctx, req)
}

func (a *searchAdapter) SearchCollection(ctx context.Context, req *SearchCollectionRequest) (*SearchResponse, error) {
	return a.inner.SearchCollection(ctx, req)
}

// --- chatAdapter ---

type chatAdapter struct {
	inner pb.ChatServiceClient
}

func (a *chatAdapter) Chat(ctx context.Context, req *ChatRequest) (ChatStream, error) {
	stream, err := a.inner.Chat(ctx, req)
	if err != nil {
		return nil, err
	}
	return &chatEventStreamAdapter{stream: stream}, nil
}

// --- embeddingAdapter ---

type embeddingAdapter struct {
	inner pb.EmbeddingServiceClient
}

func (a *embeddingAdapter) GetInfo(ctx context.Context) (*EmbeddingInfoResponse, error) {
	return a.inner.GetInfo(ctx, &GetEmbeddingInfoRequest{})
}

func (a *embeddingAdapter) TestEmbed(ctx context.Context, req *TestEmbedRequest) (*TestEmbedResponse, error) {
	return a.inner.TestEmbed(ctx, req)
}

func (a *embeddingAdapter) CompareModels(ctx context.Context, req *CompareModelsRequest) (*CompareModelsResponse, error) {
	return a.inner.CompareModels(ctx, req)
}

func (a *embeddingAdapter) SetModel(ctx context.Context, req *SetEmbedModelRequest) (*EmbeddingInfoResponse, error) {
	return a.inner.SetModel(ctx, req)
}

// --- piiAdapter ---

type piiAdapter struct {
	inner pb.PIIServiceClient
}

func (a *piiAdapter) TestMasking(ctx context.Context, req *TestMaskingRequest) (*TestMaskingResponse, error) {
	return a.inner.TestMasking(ctx, req)
}

// --- configAdapter ---

type configAdapter struct {
	inner pb.ConfigServiceClient
}

func (a *configAdapter) GetConfig(ctx context.Context) (*AppConfig, error) {
	return a.inner.GetConfig(ctx, &GetConfigRequest{})
}

func (a *configAdapter) UpdateMountedPaths(ctx context.Context, req *UpdateMountedPathsRequest) (*UpdateMountedPathsResponse, error) {
	return a.inner.UpdateMountedPaths(ctx, req)
}

func (a *configAdapter) UpdatePII(ctx context.Context, req *UpdatePIIRequest) (*PIIConfigResponse, error) {
	return a.inner.UpdatePII(ctx, req)
}

func (a *configAdapter) UpdateDocling(ctx context.Context, req *UpdateDoclingRequest) (*DoclingConfigResponse, error) {
	return a.inner.UpdateDocling(ctx, req)
}

func (a *configAdapter) UpdateDistance(ctx context.Context, req *UpdateDistanceRequest) (*UpdateDistanceResponse, error) {
	return a.inner.UpdateDistance(ctx, req)
}

func (a *configAdapter) UpdateOllama(ctx context.Context, req *UpdateOllamaRequest) (*OllamaConfigResponse, error) {
	return a.inner.UpdateOllama(ctx, req)
}

func (a *configAdapter) UpdateQdrant(ctx context.Context, req *UpdateQdrantRequest) (*QdrantConfigResponse, error) {
	return a.inner.UpdateQdrant(ctx, req)
}

func (a *configAdapter) UpdateChunking(ctx context.Context, req *UpdateChunkingRequest) (*ChunkingConfigResponse, error) {
	return a.inner.UpdateChunking(ctx, req)
}

func (a *configAdapter) UpdateImage(ctx context.Context, req *UpdateImageRequest) (*ImageConfigResponse, error) {
	return a.inner.UpdateImage(ctx, req)
}

func (a *configAdapter) GetPIIConfig(ctx context.Context) (*PIIConfigResponse, error) {
	return a.inner.GetPIIConfig(ctx, &GetPIIConfigRequest{})
}

func (a *configAdapter) GetDoclingConfig(ctx context.Context) (*DoclingConfigResponse, error) {
	return a.inner.GetDoclingConfig(ctx, &GetDoclingConfigRequest{})
}

func (a *configAdapter) ResetConfig(ctx context.Context, req *ResetConfigRequest) (*ResetConfigResponse, error) {
	return a.inner.ResetConfig(ctx, req)
}

// --- visualizationAdapter ---

type visualizationAdapter struct {
	inner pb.VisualizationServiceClient
}

func (a *visualizationAdapter) Overview(ctx context.Context, req *OverviewRequest) (*OverviewResponse, error) {
	return a.inner.Overview(ctx, req)
}

func (a *visualizationAdapter) FileTree(ctx context.Context, req *FileTreeRequest) (*FileTreeResponse, error) {
	return a.inner.FileTree(ctx, req)
}

func (a *visualizationAdapter) Vectors(ctx context.Context, req *VectorsRequest) (*VectorsResponse, error) {
	return a.inner.Vectors(ctx, req)
}

// --- smbAdapter ---

type smbAdapter struct {
	inner pb.SMBServiceClient
}

func (a *smbAdapter) TestConnection(ctx context.Context, req *SMBTestRequest) (*SMBTestResponse, error) {
	return a.inner.TestConnection(ctx, req)
}

func (a *smbAdapter) Browse(ctx context.Context, req *SMBBrowseRequest) (*SMBBrowseResponse, error) {
	return a.inner.Browse(ctx, req)
}

// --- authAdapter ---

type authAdapter struct {
	inner pb.AuthServiceClient
}

func (a *authAdapter) Login(ctx context.Context, req *LoginRequest) (*LoginResponse, error) {
	return a.inner.Login(ctx, req)
}

func (a *authAdapter) ListUsers(ctx context.Context) (*ListUsersResponse, error) {
	return a.inner.ListUsers(ctx, &ListUsersRequest{})
}

func (a *authAdapter) CreateUser(ctx context.Context, req *CreateUserRequest) (*CreateUserResponse, error) {
	return a.inner.CreateUser(ctx, req)
}

func (a *authAdapter) DeleteUser(ctx context.Context, req *DeleteUserRequest) (*DeleteUserResponse, error) {
	return a.inner.DeleteUser(ctx, req)
}

// ──────────────────────────────────────────────────────────────
// Client wraps the underlying gRPC connection and all service stubs.
// ──────────────────────────────────────────────────────────────

// Client holds the gRPC connection and typed service clients.
type Client struct {
	conn *grpc.ClientConn

	// Service stubs (all 9 services)
	Indexing      IndexingServiceClient
	Search        SearchServiceClient
	Chat          ChatServiceClient
	Embedding     EmbeddingServiceClient
	PII           PIIServiceClient
	Config        ConfigServiceClient
	Visualization VisualizationServiceClient
	SMB           SMBServiceClient
	Auth          AuthServiceClient
}

// NewClient dials the gRPC worker at the given address and returns a Client
// with all service stubs initialized. The connection is established in the
// background (no blocking dial).
func NewClient(addr string) (*Client, error) {
	conn, err := grpc.NewClient(addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("grpc dial %s: %w", addr, err)
	}

	c := &Client{
		conn:          conn,
		Indexing:      &indexingAdapter{inner: pb.NewIndexingServiceClient(conn)},
		Search:        &searchAdapter{inner: pb.NewSearchServiceClient(conn)},
		Chat:          &chatAdapter{inner: pb.NewChatServiceClient(conn)},
		Embedding:     &embeddingAdapter{inner: pb.NewEmbeddingServiceClient(conn)},
		PII:           &piiAdapter{inner: pb.NewPIIServiceClient(conn)},
		Config:        &configAdapter{inner: pb.NewConfigServiceClient(conn)},
		Visualization: &visualizationAdapter{inner: pb.NewVisualizationServiceClient(conn)},
		SMB:           &smbAdapter{inner: pb.NewSMBServiceClient(conn)},
		Auth:          &authAdapter{inner: pb.NewAuthServiceClient(conn)},
	}

	return c, nil
}

// Conn returns the underlying gRPC client connection. This can be used
// to create additional service clients if needed.
func (c *Client) Conn() *grpc.ClientConn {
	return c.conn
}

// Close closes the underlying gRPC connection.
func (c *Client) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}
