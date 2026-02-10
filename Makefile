.PHONY: proto-gen proto-go proto-py clean-proto

PROTO_DIR := proto
GO_OUT    := gateway/gen
PY_OUT    := src/ollqd_worker/gen

PROTO_FILES := $(PROTO_DIR)/ollqd/v1/types.proto $(PROTO_DIR)/ollqd/v1/processing.proto

# ── Generate all protobuf stubs ──────────────────────────

proto-gen: proto-go proto-py

# ── Go stubs ─────────────────────────────────────────────

proto-go:
	@mkdir -p $(GO_OUT)
	protoc \
		--proto_path=$(PROTO_DIR) \
		--go_out=$(GO_OUT) --go_opt=paths=source_relative \
		--go-grpc_out=$(GO_OUT) --go-grpc_opt=paths=source_relative \
		$(PROTO_FILES)
	@echo "✓ Go stubs generated in $(GO_OUT)/"

# ── Python stubs ─────────────────────────────────────────

proto-py:
	@mkdir -p $(PY_OUT)/ollqd/v1
	@touch $(PY_OUT)/__init__.py $(PY_OUT)/ollqd/__init__.py $(PY_OUT)/ollqd/v1/__init__.py
	python -m grpc_tools.protoc \
		--proto_path=$(PROTO_DIR) \
		--python_out=$(PY_OUT) \
		--grpc_python_out=$(PY_OUT) \
		--pyi_out=$(PY_OUT) \
		$(PROTO_FILES)
	@echo "✓ Python stubs generated in $(PY_OUT)/"

# ── Clean generated files ────────────────────────────────

clean-proto:
	rm -rf $(GO_OUT)/ollqd $(PY_OUT)/ollqd
	@echo "✓ Cleaned generated proto stubs"

# ── Build targets ────────────────────────────────────────

.PHONY: build-gateway build-worker

build-gateway:
	cd gateway && go build -o bin/gateway ./cmd/gateway

build-worker:
	pip install -e ".[worker]"

# ── Docker ───────────────────────────────────────────────

.PHONY: docker-build docker-up docker-down

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down
