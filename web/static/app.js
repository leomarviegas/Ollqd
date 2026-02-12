/* Ollqd WebUI — Alpine.js application */

function app() {
  return {
    loggedIn: false,
    loginForm: { username: "", password: "" },
    loginError: "",
    loginLoading: false,
    user: null,
    view: "dashboard",
    showModal: null,
    health: { ollama: false, qdrant: false },

    // User management (admin only)
    userList: [],
    newUserForm: { username: "", password: "", role: "user" },
    newUserError: "",

    // Data
    collections: [],
    models: [],
    runningModels: [],
    tasks: [],

    // Collection browse/search
    browsingCollection: null,
    browsePoints: [],
    browseNextOffset: null,
    searchingCollection: null,
    searchQuery: "",
    searchResults: [],

    // Create collection
    newCollection: { name: "", vector_size: 1024, distance: "Cosine" },

    // Model details/pull
    modelDetailName: "",
    modelDetail: null,
    pullModelName: "",
    pullProgress: null,
    pullStatus: "",

    // Chat
    chatCollection: "",
    chatModel: "",
    chatInput: "",
    chatMessages: [],
    chatStreaming: false,
    _ws: null,
    _msgCounter: 0,

    // Indexing
    mountedPaths: [],
    newMountedPath: "",
    indexTab: "codebase",
    indexForm: {
      root_path: "",
      collection: "codebase",
      chunk_size: 200,
      chunk_overlap: 40,
      incremental: true,
    },
    imageIndexForm: {
      root_path: "",
      collection: "images",
      vision_model: "",
      incremental: true,
    },

    // Upload
    uploadFiles: [],
    uploadDragging: false,
    uploadCollection: "documents",
    uploadChunkSize: 512,
    uploadChunkOverlap: 64,
    uploadSourceTag: "upload",
    uploadVisionModel: "",

    // SMB Shares
    smbShares: [],
    smbForm: { server: "", share: "", username: "", password: "", domain: "", port: 445, label: "" },
    smbTestResult: null,
    smbBrowsingShare: null,
    smbBrowsePath: "/",
    smbBrowseFiles: [],
    smbSelectedFiles: [],
    smbIndexCollection: "documents",

    // Task management
    taskFilter: "all",
    taskAutoRefresh: false,
    _taskRefreshInterval: null,
    taskDetailData: null,

    // Visualization
    vizTab: "overview",
    vizCollection: "",
    vizLoading: false,
    vizMethod: "pca",
    vizLimit: 500,
    vizFileList: [],
    vizSelectedFile: "",
    _vizLibsLoaded: false,

    // PII Masking
    piiConfig: { enabled: false, use_spacy: false, mask_embeddings: false, enabled_types: "" },
    piiTestText: "",
    piiTestResult: null,
    piiChatEnabled: false,

    // Docling / Document AI
    doclingConfig: { enabled: false, ocr_enabled: false, ocr_engine: "", table_structure: false, timeout_s: 300 },

    // Settings
    settingsTab: "general",
    settingsConfig: { qdrant: { default_distance: "Cosine" }, ollama: { local: false }, chunking: {}, image: {}, pii: {}, docling: {} },
    ollamaContainerStatus: "unknown",
    embeddingInfo: null,
    embeddingTestText: "",
    embeddingTestResult: null,
    compareModel1: "",
    compareModel2: "",
    compareText: "",
    compareResult: null,
    switchEmbedModel: "",

    // Navigation
    nav: [
      { id: "dashboard",   icon: "fa-solid fa-gauge-high",    label: "Dashboard",   load: () => {} },
      { id: "collections", icon: "fa-solid fa-database",      label: "Collections", load: () => {} },
      { id: "models",      icon: "fa-solid fa-cube",          label: "Models",      load: () => {} },
      { id: "chat",        icon: "fa-solid fa-comments",      label: "RAG Chat",    load: () => {} },
      { id: "indexing",    icon: "fa-solid fa-layer-group",   label: "Indexing",    load: () => {} },
      { id: "visualize",   icon: "fa-solid fa-project-diagram", label: "Visualize", load: () => {} },
      { id: "settings",    icon: "fa-solid fa-gear",          label: "Settings",    load: () => {} },
    ],

    // ── Init ──────────────────────────────────────────────────

    async init() {
      this.nav = [
        { id: "dashboard",   icon: "fa-solid fa-gauge-high",    label: "Dashboard",   load: () => this.loadDashboard() },
        { id: "collections", icon: "fa-solid fa-database",      label: "Collections", load: () => this.loadCollections() },
        { id: "models",      icon: "fa-solid fa-cube",          label: "Models",      load: () => this.loadModels() },
        { id: "chat",        icon: "fa-solid fa-comments",      label: "RAG Chat",    load: () => this.ensureWebSocket() },
        { id: "indexing",    icon: "fa-solid fa-layer-group",   label: "Indexing",    load: () => this.loadTasks() },
        { id: "visualize",   icon: "fa-solid fa-project-diagram", label: "Visualize", load: () => this.loadVizTab() },
        { id: "smb",         icon: "fa-solid fa-network-wired", label: "SMB Shares",  load: () => this.loadSMBShares() },
        { id: "settings",    icon: "fa-solid fa-gear",          label: "Settings",    load: () => this.loadSettings() },
      ];
      // Check if already logged in (cookie-based)
      try {
        const r = await fetch("/api/auth/me");
        if (r.ok) {
          this.user = await r.json();
          this.loggedIn = true;
          await this.loadDashboard();
        }
      } catch {}
    },

    async handleLogin() {
      if (!this.loginForm.username.trim() || !this.loginForm.password.trim()) {
        this.loginError = "Please enter username and password";
        return;
      }
      this.loginError = "";
      this.loginLoading = true;
      try {
        const r = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.loginForm),
        });
        const data = await r.json();
        if (!r.ok) {
          this.loginError = data.detail || "Login failed";
          return;
        }
        this.user = { username: data.username, role: data.role };
        this.loggedIn = true;
        this.loginForm = { username: "", password: "" };
        await this.loadDashboard();
      } catch (e) {
        this.loginError = "Connection error — is the server running?";
      } finally {
        this.loginLoading = false;
      }
    },

    async handleLogout() {
      try { await fetch("/api/auth/logout", { method: "POST" }); } catch {}
      this.loggedIn = false;
      this.user = null;
      this.loginForm = { username: "", password: "" };
    },

    // ── User Management (admin) ──────────────────────────────

    async loadUsers() {
      try {
        const r = await fetch("/api/users");
        if (r.ok) {
          const data = await r.json();
          this.userList = data.users || [];
        }
      } catch {}
    },

    async createUser() {
      this.newUserError = "";
      if (!this.newUserForm.username.trim() || !this.newUserForm.password.trim()) {
        this.newUserError = "Username and password are required";
        return;
      }
      try {
        const r = await fetch("/api/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.newUserForm),
        });
        if (!r.ok) {
          const data = await r.json();
          this.newUserError = data.detail || "Failed to create user";
          return;
        }
        this.newUserForm = { username: "", password: "", role: "user" };
        await this.loadUsers();
      } catch (e) {
        this.newUserError = "Connection error";
      }
    },

    async deleteUser(username) {
      if (!confirm(`Delete user "${username}"?`)) return;
      try {
        const r = await fetch(`/api/users/${encodeURIComponent(username)}`, { method: "DELETE" });
        if (!r.ok) {
          const data = await r.json();
          alert(data.detail || "Failed to delete user");
          return;
        }
        await this.loadUsers();
      } catch (e) {
        alert("Connection error");
      }
    },

    async loadDashboard() {
      await Promise.all([
        this.loadHealth(),
        this.loadCollections(),
        this.loadModels(),
        this.loadMountedPaths(),
      ]);
    },

    async loadMountedPaths() {
      try {
        const r = await fetch("/api/system/config");
        const d = await r.json();
        this.mountedPaths = d.mounted_paths || [];
      } catch {
        this.mountedPaths = [];
      }
    },

    async _saveMountedPaths(paths) {
      try {
        const r = await fetch("/api/system/config/mounted-paths", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paths }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this.mountedPaths = d.mounted_paths;
      } catch (e) {
        alert("Failed to update paths: " + e.message);
      }
    },

    async addMountedPath() {
      const p = this.newMountedPath.trim();
      if (!p) return;
      if (this.mountedPaths.includes(p)) {
        this.newMountedPath = "";
        return;
      }
      await this._saveMountedPaths([...this.mountedPaths, p]);
      this.newMountedPath = "";
    },

    async removeMountedPath(path) {
      await this._saveMountedPaths(this.mountedPaths.filter((p) => p !== path));
    },

    // ── Health ────────────────────────────────────────────────

    async loadHealth() {
      try {
        const r = await fetch("/api/system/health");
        const d = await r.json();
        this.health.ollama = d.ollama?.status === "ok";
        this.health.qdrant = d.qdrant?.status === "ok";
      } catch {
        this.health.ollama = false;
        this.health.qdrant = false;
      }
    },

    // ── Collections ───────────────────────────────────────────

    async loadCollections() {
      try {
        const r = await fetch("/api/qdrant/collections");
        const d = await r.json();
        this.collections = d.collections || [];
        if (this.collections.length && !this.chatCollection) {
          this.chatCollection = this.collections[0].name;
        }
        if (this.collections.length && !this.vizCollection) {
          this.vizCollection = this.collections[0].name;
        }
      } catch {
        this.collections = [];
      }
    },

    async createCollection() {
      try {
        const r = await fetch("/api/qdrant/collections", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.newCollection),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        this.showModal = null;
        this.newCollection = { name: "", vector_size: 1024, distance: "Cosine" };
        await this.loadCollections();
      } catch (e) {
        alert("Failed: " + e.message);
      }
    },

    confirmDeleteCollection(name) {
      if (!confirm(`Delete collection "${name}"? This cannot be undone.`)) return;
      fetch(`/api/qdrant/collections/${encodeURIComponent(name)}`, { method: "DELETE" })
        .then(() => this.loadCollections())
        .catch((e) => alert("Delete failed: " + e.message));
    },

    async browseCollection(name) {
      this.browsingCollection = name;
      this.browsePoints = [];
      this.browseNextOffset = null;
      this.searchingCollection = null;
      try {
        const r = await fetch(`/api/qdrant/collections/${encodeURIComponent(name)}/points?limit=20`);
        const d = await r.json();
        this.browsePoints = d.points || [];
        this.browseNextOffset = d.next_offset || null;
      } catch (e) {
        alert("Browse failed: " + e.message);
      }
    },

    async loadMorePoints() {
      if (!this.browseNextOffset || !this.browsingCollection) return;
      try {
        const r = await fetch(
          `/api/qdrant/collections/${encodeURIComponent(this.browsingCollection)}/points?limit=20&offset=${this.browseNextOffset}`
        );
        const d = await r.json();
        this.browsePoints.push(...(d.points || []));
        this.browseNextOffset = d.next_offset || null;
      } catch (e) {
        alert("Load more failed: " + e.message);
      }
    },

    searchInCollection(name) {
      this.searchingCollection = name;
      this.searchResults = [];
      this.searchQuery = "";
      this.browsingCollection = null;
    },

    async runCollectionSearch() {
      if (!this.searchQuery.trim() || !this.searchingCollection) return;
      try {
        const r = await fetch(`/api/qdrant/collections/${encodeURIComponent(this.searchingCollection)}/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: this.searchQuery, top_k: 10 }),
        });
        const d = await r.json();
        this.searchResults = d.results || [];
      } catch (e) {
        alert("Search failed: " + e.message);
      }
    },

    // ── Models ────────────────────────────────────────────────

    async loadModels() {
      try {
        const r = await fetch("/api/ollama/models");
        const d = await r.json();
        this.models = d.models || [];
        if (this.models.length && !this.chatModel) {
          const chat = this.models.find((m) => !m.name.includes("embed"));
          this.chatModel = chat ? chat.name : this.models[0].name;
        }
      } catch {
        this.models = [];
      }
    },

    async loadRunningModels() {
      try {
        const r = await fetch("/api/ollama/ps");
        const d = await r.json();
        this.runningModels = d.models || [];
      } catch {
        this.runningModels = [];
      }
    },

    async showModelDetails(name) {
      this.modelDetailName = name;
      this.modelDetail = null;
      this.showModal = "model-details";
      try {
        const r = await fetch("/api/ollama/models/show", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        this.modelDetail = await r.json();
      } catch (e) {
        this.modelDetail = { error: e.message };
      }
    },

    confirmDeleteModel(name) {
      if (!confirm(`Delete model "${name}"?`)) return;
      fetch(`/api/ollama/models/${encodeURIComponent(name)}`, { method: "DELETE" })
        .then(() => this.loadModels())
        .catch((e) => alert("Delete failed: " + e.message));
    },

    async pullModel() {
      const name = this.pullModelName.trim();
      if (!name) return;
      this.showModal = null;
      this.pullProgress = 0;
      this.pullStatus = "Starting...";

      try {
        const r = await fetch("/api/ollama/models/pull", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });

        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });

          const lines = buf.split("\n");
          buf = lines.pop();

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6).trim();
            if (payload === "[DONE]") {
              this.pullProgress = null;
              this.pullStatus = "";
              this.pullModelName = "";
              await this.loadModels();
              return;
            }
            try {
              const d = JSON.parse(payload);
              this.pullStatus = d.status || "";
              if (d.total && d.completed) {
                this.pullProgress = Math.round((d.completed / d.total) * 100);
              }
            } catch {}
          }
        }
      } catch (e) {
        this.pullStatus = "Error: " + e.message;
      }
      this.pullProgress = null;
      await this.loadModels();
    },

    // ── RAG Chat (WebSocket) ──────────────────────────────────

    ensureWebSocket() {
      if (this._ws && this._ws.readyState <= 1) return;
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      this._ws = new WebSocket(`${proto}//${location.host}/api/rag/ws`);

      this._ws.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        const last = this.chatMessages[this.chatMessages.length - 1];

        if (data.type === "chunk") {
          if (last && last.role === "assistant" && last.streaming) {
            last.content += data.content;
            last.html = this._renderMarkdown(last.content);
          }
        } else if (data.type === "sources") {
          if (last && last.role === "assistant") {
            last.sources = data.results || [];
          }
        } else if (data.type === "done") {
          if (last && last.role === "assistant") {
            last.streaming = false;
            if (data.pii_masked) {
              last.piiMasked = true;
              last.piiEntitiesCount = data.pii_entities_count || 0;
            }
          }
          this.chatStreaming = false;
        } else if (data.type === "error") {
          if (last && last.role === "assistant") {
            last.content += "\n\n**Error:** " + data.content;
            last.html = this._renderMarkdown(last.content);
            last.streaming = false;
          }
          this.chatStreaming = false;
        }

        this.$nextTick(() => {
          const box = this.$refs.chatBox;
          if (box) box.scrollTop = box.scrollHeight;
        });
      };

      this._ws.onclose = () => {
        this.chatStreaming = false;
      };
    },

    sendChat() {
      const msg = this.chatInput.trim();
      if (!msg || this.chatStreaming) return;
      this.ensureWebSocket();

      this.chatMessages.push({
        id: ++this._msgCounter,
        role: "user",
        content: msg,
        html: this._escapeHtml(msg),
      });

      this.chatMessages.push({
        id: ++this._msgCounter,
        role: "assistant",
        content: "",
        html: "",
        streaming: true,
        sources: [],
      });

      this.chatInput = "";
      this.chatStreaming = true;

      const send = () => {
        this._ws.send(JSON.stringify({
          message: msg,
          collection: this.chatCollection,
          model: this.chatModel,
          pii_enabled: this.piiChatEnabled,
        }));
      };

      if (this._ws.readyState === 1) {
        send();
      } else {
        this._ws.addEventListener("open", send, { once: true });
      }

      this.$nextTick(() => {
        const box = this.$refs.chatBox;
        if (box) box.scrollTop = box.scrollHeight;
      });
    },

    clearChat() {
      this.chatMessages = [];
      this._msgCounter = 0;
      if (this._ws) {
        this._ws.close();
        this._ws = null;
      }
    },

    // ── Indexing ──────────────────────────────────────────────

    async startIndexCodebase() {
      try {
        const r = await fetch("/api/rag/index/codebase", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.indexForm),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this._pollTask(d.task_id);
        await this.loadTasks();
      } catch (e) {
        alert("Indexing failed: " + e.message);
      }
    },

    // ── Upload Methods ─────────────────────────────────────────

    handleUploadDrop(e) {
      e.preventDefault();
      this.uploadDragging = false;
      const files = [...e.dataTransfer.files];
      this.uploadFiles = [...this.uploadFiles, ...files];
    },

    handleUploadSelect(e) {
      const files = [...e.target.files];
      this.uploadFiles = [...this.uploadFiles, ...files];
      e.target.value = "";
    },

    removeUploadFile(index) {
      this.uploadFiles.splice(index, 1);
    },

    async startUpload() {
      if (!this.uploadFiles.length) return;
      const formData = new FormData();
      for (const f of this.uploadFiles) {
        formData.append("files", f);
      }
      formData.append("collection", this.uploadCollection);
      formData.append("chunk_size", this.uploadChunkSize);
      formData.append("chunk_overlap", this.uploadChunkOverlap);
      formData.append("source_tag", this.uploadSourceTag);
      if (this.uploadVisionModel) {
        formData.append("vision_model", this.uploadVisionModel);
      }

      try {
        const r = await fetch("/api/rag/upload", {
          method: "POST",
          body: formData,
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this.uploadFiles = [];
        this.uploadVisionModel = "";
        this._pollTask(d.task_id);
        await this.loadTasks();
      } catch (e) {
        alert("Upload failed: " + e.message);
      }
    },

    async startIndexImages() {
      try {
        const r = await fetch("/api/rag/index/images", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            root_path: this.imageIndexForm.root_path,
            collection: this.imageIndexForm.collection,
            vision_model: this.imageIndexForm.vision_model || undefined,
            incremental: this.imageIndexForm.incremental,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this._pollTask(d.task_id);
        await this.loadTasks();
      } catch (e) {
        alert("Image indexing failed: " + e.message);
      }
    },

    async loadTasks() {
      try {
        const r = await fetch("/api/rag/tasks");
        const d = await r.json();
        this.tasks = Array.isArray(d) ? d : d.tasks || [];
      } catch {
        this.tasks = [];
      }
    },

    async clearTasks() {
      try {
        await fetch("/api/rag/tasks", { method: "DELETE" });
        await this.loadTasks();
      } catch (e) {
        alert("Clear failed: " + e.message);
      }
    },

    async cancelTask(taskId) {
      try {
        const r = await fetch(`/api/rag/tasks/${taskId}/cancel`, { method: "POST" });
        if (!r.ok) throw new Error((await r.json()).detail);
        await this.loadTasks();
      } catch (e) {
        alert("Cancel failed: " + e.message);
      }
    },

    async retryTask(taskId) {
      try {
        const r = await fetch(`/api/rag/tasks/${taskId}/retry`, { method: "POST" });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this._pollTask(d.task_id);
        await this.loadTasks();
      } catch (e) {
        alert("Retry failed: " + e.message);
      }
    },

    showTaskDetail(task) {
      this.taskDetailData = task;
      this.showModal = "task-detail";
    },

    get filteredTasks() {
      if (this.taskFilter === "all") return this.tasks;
      return this.tasks.filter((t) => t.status === this.taskFilter);
    },

    toggleTaskAutoRefresh() {
      this.taskAutoRefresh = !this.taskAutoRefresh;
      if (this.taskAutoRefresh) {
        this._taskRefreshInterval = setInterval(() => this.loadTasks(), 2000);
      } else {
        clearInterval(this._taskRefreshInterval);
        this._taskRefreshInterval = null;
      }
    },

    formatDuration(ms) {
      if (!ms) return "—";
      if (ms < 1000) return ms + "ms";
      if (ms < 60000) return (ms / 1000).toFixed(1) + "s";
      return (ms / 60000).toFixed(1) + "m";
    },

    _pollTask(taskId) {
      const poll = async () => {
        try {
          const r = await fetch(`/api/rag/tasks/${taskId}`);
          const t = await r.json();
          const idx = this.tasks.findIndex((x) => x.id === taskId);
          if (idx >= 0) {
            this.tasks[idx] = t;
          } else {
            this.tasks.unshift(t);
          }
          if (t.status === "running" || t.status === "pending") {
            setTimeout(poll, 1000);
          } else {
            await this.loadCollections();
          }
        } catch {
          // Task gone
        }
      };
      setTimeout(poll, 500);
    },

    // ── Visualization ─────────────────────────────────────────

    async loadVizTab() {
      await this.loadCollections();
      if (!this._vizLibsLoaded) {
        await this._loadVizLibs();
      }
    },

    async _loadVizLibs() {
      const loadScript = (url) => new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${url}"]`)) { resolve(); return; }
        const s = document.createElement("script");
        s.src = url;
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      });
      const loadCSS = (url) => new Promise((resolve) => {
        if (document.querySelector(`link[href="${url}"]`)) { resolve(); return; }
        const l = document.createElement("link");
        l.rel = "stylesheet";
        l.href = url;
        l.onload = resolve;
        document.head.appendChild(l);
      });
      try {
        await Promise.all([
          loadScript("https://unpkg.com/vis-network@9.1.2/dist/vis-network.min.js"),
          loadCSS("https://unpkg.com/vis-network@9.1.2/dist/dist/vis-network.min.css"),
          loadScript("https://cdn.plot.ly/plotly-gl3d-2.27.0.min.js"),
        ]);
        this._vizLibsLoaded = true;
      } catch (e) {
        console.warn("Failed to load viz libs:", e);
      }
    },

    async loadVizOverview() {
      if (!this.vizCollection) return;
      this.vizLoading = true;
      try {
        const r = await fetch(`/api/rag/visualize/${encodeURIComponent(this.vizCollection)}/overview?limit=${this.vizLimit}`);
        const d = await r.json();

        // Build file list for File Tree tab
        this.vizFileList = d.nodes.filter(n => n.file_path).map(n => n.file_path);

        this.$nextTick(() => {
          const container = document.getElementById("viz-overview-container");
          if (!container || !window.vis) return;
          const network = new vis.Network(container, {
            nodes: new vis.DataSet(d.nodes),
            edges: new vis.DataSet(d.edges),
          }, {
            physics: { barnesHut: { gravitationalConstant: -3000, springLength: 150 } },
            nodes: { font: { size: 12, color: "#333" }, borderWidth: 2 },
            edges: { color: { color: "#ccc" }, width: 1 },
            interaction: { hover: true, tooltipDelay: 100 },
          });
          container._vizStats = d.stats;
        });
      } catch (e) {
        alert("Visualization failed: " + e.message);
      }
      this.vizLoading = false;
    },

    async loadVizVectors() {
      if (!this.vizCollection) return;
      this.vizLoading = true;
      try {
        const r = await fetch(`/api/rag/visualize/${encodeURIComponent(this.vizCollection)}/vectors?method=${this.vizMethod}&dims=3&limit=${this.vizLimit}`);
        if (!r.ok) {
          const err = await r.json();
          alert(err.detail || "Failed to load vectors");
          this.vizLoading = false;
          return;
        }
        const d = await r.json();

        this.$nextTick(() => {
          const container = document.getElementById("viz-vectors-container");
          if (!container || !window.Plotly) return;
          const trace = {
            x: d.points.map(p => p.x),
            y: d.points.map(p => p.y),
            z: d.points.map(p => p.z),
            mode: "markers",
            type: "scatter3d",
            marker: {
              size: 3,
              color: d.points.map(p => p.color),
              opacity: 0.8,
            },
            text: d.points.map(p => `${p.file.split("/").pop()} [${p.language}] chunk ${p.chunk}`),
            hoverinfo: "text",
          };
          Plotly.newPlot(container, [trace], {
            title: `${d.method.toUpperCase()} — ${d.total_points} vectors (${d.original_dims}D → 3D)`,
            scene: { xaxis: { title: "PC1" }, yaxis: { title: "PC2" }, zaxis: { title: "PC3" } },
            margin: { l: 0, r: 0, b: 0, t: 40 },
          }, { responsive: true });
        });
      } catch (e) {
        alert("Vector visualization failed: " + e.message);
      }
      this.vizLoading = false;
    },

    async loadVizFileTree() {
      if (!this.vizCollection || !this.vizSelectedFile) return;
      this.vizLoading = true;
      try {
        const r = await fetch(`/api/rag/visualize/${encodeURIComponent(this.vizCollection)}/file-tree?file_path=${encodeURIComponent(this.vizSelectedFile)}`);
        const d = await r.json();

        this.$nextTick(() => {
          const container = document.getElementById("viz-filetree-container");
          if (!container || !window.vis) return;
          new vis.Network(container, {
            nodes: new vis.DataSet(d.nodes),
            edges: new vis.DataSet(d.edges),
          }, {
            layout: { hierarchical: { direction: "UD", sortMethod: "directed", nodeSpacing: 120 } },
            nodes: { font: { size: 12 }, borderWidth: 2 },
            edges: { color: { color: "#999" }, arrows: { to: true } },
            interaction: { hover: true, tooltipDelay: 100 },
            physics: false,
          });
        });
      } catch (e) {
        alert("File tree failed: " + e.message);
      }
      this.vizLoading = false;
    },

    // ── Settings ──────────────────────────────────────────────

    async loadSettings() {
      try {
        const r = await fetch("/api/system/config");
        this.settingsConfig = await r.json();
        this.mountedPaths = this.settingsConfig.mounted_paths || [];
        this.checkOllamaContainer();
      } catch (e) {
        console.error("Failed to load settings:", e);
      }
    },

    async loadEmbeddingInfo() {
      this.embeddingInfo = null;
      try {
        const r = await fetch("/api/system/config/embedding");
        this.embeddingInfo = await r.json();
      } catch (e) {
        this.embeddingInfo = { error: e.message };
      }
    },

    async switchEmbeddingModel() {
      if (!this.switchEmbedModel) return;
      try {
        const r = await fetch("/api/system/config/embedding", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: this.switchEmbedModel }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this.embeddingInfo = d;
        this.switchEmbedModel = "";
        await this.loadSettings();
        alert(`Switched to ${d.model} (${d.dimension}D, ${d.latency_ms}ms)`);
      } catch (e) {
        alert("Switch failed: " + e.message);
      }
    },

    async testEmbedding() {
      if (!this.embeddingTestText.trim()) return;
      this.embeddingTestResult = null;
      try {
        const r = await fetch("/api/system/config/embedding/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: this.embeddingTestText }),
        });
        this.embeddingTestResult = await r.json();
      } catch (e) {
        this.embeddingTestResult = { error: e.message };
      }
    },

    async compareEmbeddings() {
      if (!this.compareText.trim() || !this.compareModel1 || !this.compareModel2) return;
      this.compareResult = null;
      try {
        const r = await fetch("/api/system/config/embedding/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: this.compareText,
            model1: this.compareModel1,
            model2: this.compareModel2,
          }),
        });
        this.compareResult = await r.json();
      } catch (e) {
        this.compareResult = { error: e.message };
      }
    },

    async saveOllamaConfig() {
      if (!this.settingsConfig) return;
      try {
        const r = await fetch("/api/system/config/ollama", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            base_url: this.settingsConfig.ollama.base_url,
            chat_model: this.settingsConfig.ollama.chat_model,
            embed_model: this.settingsConfig.ollama.embed_model,
            vision_model: this.settingsConfig.ollama.vision_model,
            timeout_s: this.settingsConfig.ollama.timeout_s,
            local: this.settingsConfig.ollama.local,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this.settingsConfig.ollama = { ...this.settingsConfig.ollama, ...d };
        alert("Ollama settings saved");
      } catch (e) {
        alert("Save failed: " + e.message);
      }
    },

    async checkOllamaContainer() {
      try {
        const r = await fetch("/api/system/ollama/container");
        const d = await r.json();
        this.ollamaContainerStatus = d.status || "unknown";
      } catch {
        this.ollamaContainerStatus = "unknown";
      }
    },

    async toggleOllamaLocal() {
      const goingLocal = !this.settingsConfig.ollama.local;

      try {
        if (goingLocal) {
          // Start container
          this.ollamaContainerStatus = "starting";
          const r = await fetch("/api/system/ollama/container", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "start" }),
          });
          if (!r.ok) throw new Error((await r.json()).detail);
          const d = await r.json();
          this.ollamaContainerStatus = d.status;

          // Update config: set local=true, base_url to Docker internal
          this.settingsConfig.ollama.local = true;
          this.settingsConfig.ollama.base_url = "http://host.docker.internal:11434";
          await this.saveOllamaConfig();
        } else {
          // Stop container
          this.ollamaContainerStatus = "stopping";
          const r = await fetch("/api/system/ollama/container", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "stop" }),
          });
          if (!r.ok) throw new Error((await r.json()).detail);
          const d = await r.json();
          this.ollamaContainerStatus = d.status;

          // Update config: set local=false
          this.settingsConfig.ollama.local = false;
          await this.saveOllamaConfig();
        }
      } catch (e) {
        alert("Toggle failed: " + e.message);
        await this.checkOllamaContainer();
      }
    },

    async saveQdrantConfig() {
      if (!this.settingsConfig) return;
      try {
        const r = await fetch("/api/system/config/qdrant", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: this.settingsConfig.qdrant.url,
            default_collection: this.settingsConfig.qdrant.default_collection,
            default_distance: this.settingsConfig.qdrant.default_distance,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this.settingsConfig.qdrant = { ...this.settingsConfig.qdrant, ...d };
        alert("Qdrant settings saved");
      } catch (e) {
        alert("Save failed: " + e.message);
      }
    },

    async saveChunkingConfig() {
      if (!this.settingsConfig) return;
      try {
        const r = await fetch("/api/system/config/chunking", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chunk_size: this.settingsConfig.chunking.chunk_size,
            chunk_overlap: this.settingsConfig.chunking.chunk_overlap,
            max_file_size_kb: this.settingsConfig.chunking.max_file_size_kb,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this.settingsConfig.chunking = { ...this.settingsConfig.chunking, ...d };
        alert("Chunking settings saved");
      } catch (e) {
        alert("Save failed: " + e.message);
      }
    },

    async saveImageConfig() {
      if (!this.settingsConfig) return;
      try {
        const r = await fetch("/api/system/config/image", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            max_image_size_kb: this.settingsConfig.image.max_image_size_kb,
            caption_prompt: this.settingsConfig.image.caption_prompt,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this.settingsConfig.image = { ...this.settingsConfig.image, ...d };
        alert("Image settings saved");
      } catch (e) {
        alert("Save failed: " + e.message);
      }
    },

    async saveDistanceMetric() {
      if (!this.settingsConfig) return;
      try {
        const r = await fetch("/api/system/config/distance", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ distance: this.settingsConfig.qdrant.default_distance }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        alert("Distance metric updated (applies to new collections)");
      } catch (e) {
        alert("Save failed: " + e.message);
      }
    },

    // ── PII Masking ─────────────────────────────────────────────

    async loadPIIConfig() {
      try {
        const r = await fetch("/api/system/config/pii");
        this.piiConfig = await r.json();
        this.piiChatEnabled = this.piiConfig.enabled;
      } catch (e) {
        this.piiConfig = { error: e.message };
      }
    },

    async savePIIConfig() {
      if (!this.piiConfig) return;
      try {
        const r = await fetch("/api/system/config/pii", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            enabled: this.piiConfig.enabled,
            use_spacy: this.piiConfig.use_spacy,
            mask_embeddings: this.piiConfig.mask_embeddings,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        this.piiConfig = await r.json();
        this.piiChatEnabled = this.piiConfig.enabled;
        alert("PII settings saved");
      } catch (e) {
        alert("Save failed: " + e.message);
      }
    },

    // ── Docling / Document AI ─────────────────────────────────

    async loadDoclingConfig() {
      try {
        const r = await fetch("/api/system/config/docling");
        this.doclingConfig = await r.json();
      } catch (e) {
        this.doclingConfig = { error: e.message };
      }
    },

    async updateDoclingConfig() {
      if (!this.doclingConfig) return;
      try {
        const r = await fetch("/api/system/config/docling", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            enabled: this.doclingConfig.enabled,
            ocr_enabled: this.doclingConfig.ocr_enabled,
            ocr_engine: this.doclingConfig.ocr_engine,
            table_structure: this.doclingConfig.table_structure,
            timeout_s: this.doclingConfig.timeout_s,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        this.doclingConfig = { ...this.doclingConfig, ...(await r.json()) };
        alert("Document AI settings saved");
      } catch (e) {
        alert("Save failed: " + e.message);
      }
    },

    async resetConfig(section) {
      const label = section === 'all' ? 'ALL settings' : section + ' settings';
      if (!confirm(`Reset ${label} to defaults? This removes all saved overrides.`)) return;
      try {
        const r = await fetch(`/api/system/config/${section}`, { method: "DELETE" });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        alert(`Reset ${d.section}: ${(d.reset_keys || []).length} override(s) removed`);
        await this.loadSettings();
        if (section === 'pii' || section === 'all') await this.loadPIIConfig();
        if (section === 'docling' || section === 'all') await this.loadDoclingConfig();
      } catch (e) {
        alert("Reset failed: " + e.message);
      }
    },

    async testPIIMasking() {
      if (!this.piiTestText.trim()) return;
      this.piiTestResult = null;
      try {
        const r = await fetch("/api/system/config/pii/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: this.piiTestText }),
        });
        this.piiTestResult = await r.json();
      } catch (e) {
        this.piiTestResult = { error: e.message };
      }
    },

    // ── SMB Methods ───────────────────────────────────────────

    async loadSMBShares() {
      try {
        const r = await fetch("/api/smb/shares");
        const d = await r.json();
        this.smbShares = d.shares || [];
      } catch { this.smbShares = []; }
    },

    async testSMBConnection() {
      this.smbTestResult = null;
      try {
        const r = await fetch("/api/smb/shares/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.smbForm),
        });
        this.smbTestResult = await r.json();
      } catch (e) {
        this.smbTestResult = { ok: false, error: e.message };
      }
    },

    async addSMBShare() {
      try {
        const r = await fetch("/api/smb/shares", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.smbForm),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        this.smbForm = { server: "", share: "", username: "", password: "", domain: "", port: 445, label: "" };
        this.smbTestResult = null;
        await this.loadSMBShares();
      } catch (e) { alert("Failed: " + e.message); }
    },

    async removeSMBShare(id) {
      if (!confirm("Remove this share?")) return;
      await fetch(`/api/smb/shares/${id}`, { method: "DELETE" });
      await this.loadSMBShares();
    },

    async browseSMBShare(shareId, path = "/") {
      this.smbBrowsingShare = shareId;
      this.smbBrowsePath = path;
      this.smbSelectedFiles = [];
      try {
        const r = await fetch(`/api/smb/shares/${shareId}/browse`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this.smbBrowseFiles = d.files || [];
      } catch (e) { alert("Browse failed: " + e.message); }
    },

    toggleSMBFileSelect(filePath) {
      const i = this.smbSelectedFiles.indexOf(filePath);
      if (i >= 0) this.smbSelectedFiles.splice(i, 1);
      else this.smbSelectedFiles.push(filePath);
    },

    async indexSMBFiles() {
      if (!this.smbSelectedFiles.length || !this.smbBrowsingShare) return;
      try {
        const r = await fetch(`/api/smb/shares/${this.smbBrowsingShare}/index`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            remote_paths: this.smbSelectedFiles,
            collection: this.smbIndexCollection,
          }),
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        this._pollTask(d.task_id);
        this.smbSelectedFiles = [];
        await this.loadTasks();
      } catch (e) { alert("Index failed: " + e.message); }
    },

    // ── Helpers ───────────────────────────────────────────────

    formatBytes(bytes) {
      if (!bytes) return "—";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let i = 0;
      let val = bytes;
      while (val >= 1024 && i < units.length - 1) {
        val /= 1024;
        i++;
      }
      return val.toFixed(i > 1 ? 1 : 0) + " " + units[i];
    },

    _escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    },

    _renderMarkdown(text) {
      let html = this._escapeHtml(text);
      html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre><code>${code}</code></pre>`;
      });
      html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
      html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
      html = html.replace(/\n/g, "<br>");
      return html;
    },
  };
}
