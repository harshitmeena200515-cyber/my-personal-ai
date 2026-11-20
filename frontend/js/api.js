/**
 * MY PERSONAL AI — Core API Client
 * Connects directly to local FastAPI endpoints without external dependencies.
 */

class ApiClient {
  constructor(baseUrl = "") {
    this.baseUrl = baseUrl;
    this.token = localStorage.getItem("session_token") || null;
  }

  setToken(token) {
    this.token = token;
    if (token) {
      localStorage.setItem("session_token", token);
    } else {
      localStorage.removeItem("session_token");
    }
  }

  getHeaders(extraHeaders = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...extraHeaders,
    };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }
    return headers;
  }

  async request(path, options = {}) {
    const url = `${this.baseUrl}${path}`;
    const headers = this.getHeaders(options.headers || {});
    const config = {
      ...options,
      headers,
    };

    const response = await fetch(url, config);

    // If 401 Unauthorized, clear stale session token
    if (response.status === 401 && path !== "/api/v1/auth/login" && path !== "/api/v1/auth/register") {
      this.setToken(null);
      window.dispatchEvent(new CustomEvent("auth:required"));
    }

    if (!response.ok) {
      let detail = `Request failed with status ${response.status}`;
      try {
        const errorJson = await response.json();
        detail = errorJson.detail || detail;
      } catch (e) {
        // Fallback to text
      }
      const err = new Error(detail);
      err.status = response.status;
      throw err;
    }

    // If No Content (204)
    if (response.status === 204) {
      return null;
    }

    return await response.json();
  }

  // --- Auth Endpoints ---

  async register(username, password) {
    const res = await this.request("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (res.token) {
      this.setToken(res.token);
    }
    return res;
  }

  async login(username, password) {
    const res = await this.request("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (res.token) {
      this.setToken(res.token);
    }
    return res;
  }

  async logout() {
    try {
      await this.request("/api/v1/auth/logout", { method: "POST" });
    } finally {
      this.setToken(null);
    }
  }

  async getMe() {
    return await this.request("/api/v1/auth/me");
  }

  // --- Conversations Endpoints ---

  async listConversations() {
    return await this.request("/api/v1/conversations");
  }

  async createConversation(title = "New Conversation") {
    return await this.request("/api/v1/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  }

  async getConversation(id) {
    return await this.request(`/api/v1/conversations/${id}`);
  }

  async updateConversationTitle(id, title) {
    return await this.request(`/api/v1/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
  }

  async deleteConversation(id) {
    return await this.request(`/api/v1/conversations/${id}`, {
      method: "DELETE",
    });
  }

  async getMessages(conversationId) {
    return await this.request(`/api/v1/conversations/${conversationId}/messages`);
  }

  async addMessage(conversationId, role, content, reasoning = null) {
    return await this.request(`/api/v1/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ role, content, reasoning }),
    });
  }

  // --- Tasks & Tools ---

  async listTasks() {
    return await this.request("/api/v1/tasks");
  }

  async listTools() {
    return await this.request("/api/v1/tools");
  }

  // --- System & Hardware ---

  async getHealth() {
    return await this.request("/health");
  }

  async getSystemInfo() {
    return await this.request("/api/v1/system/info");
  }

  async getModels() {
    return await this.request("/api/v1/models");
  }

  async sendChat(payload) {
    return await this.request("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  // --- Real Streaming Endpoints (SSE) ---

  async streamChat(payload, { onChunk, onDone, onError, signal }) {
    const url = `${this.baseUrl}/api/v1/chat`;
    const headers = this.getHeaders();

    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({ ...payload, stream: true }),
        signal,
      });

      if (!response.ok) {
        if (response.status === 401) {
          this.setToken(null);
          window.dispatchEvent(new CustomEvent("auth:required"));
        }
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `Chat request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // Keep partial line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const dataStr = trimmed.slice(6);
          if (dataStr === "[DONE]") {
            if (onDone) onDone();
            return;
          }
          if (onChunk) onChunk(dataStr);
        }
      }

      if (onDone) onDone();
    } catch (err) {
      if (err.name !== "AbortError" && onError) {
        onError(err);
      }
    }
  }

  async streamThink(message, conversationId, { onEvent, onDone, onError, signal }) {
    const url = `${this.baseUrl}/api/v1/think`;
    const headers = this.getHeaders();

    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({ message, conversation_id: conversationId, stream: true }),
        signal,
      });

      if (!response.ok) {
        if (response.status === 401) {
          this.setToken(null);
          window.dispatchEvent(new CustomEvent("auth:required"));
        }
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `Think request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const dataStr = trimmed.slice(6);
          if (dataStr === "[DONE]") {
            if (onDone) onDone();
            return;
          }
          try {
            const eventObj = JSON.parse(dataStr);
            if (onEvent) onEvent(eventObj);
          } catch (e) {
            // raw string chunk
            if (onEvent) onEvent({ phase: "token", text: dataStr });
          }
        }
      }

      if (onDone) onDone();
    } catch (err) {
      if (err.name !== "AbortError" && onError) {
        onError(err);
      }
    }
  }

  // --- Security & HITL Endpoints ---

  async getApprovals(status = null) {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return await this.request(`/api/v1/security/approvals${query}`);
  }

  async resolveApproval(approvalId, approved) {
    return await this.request(`/api/v1/security/approvals/${approvalId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ approved }),
    });
  }

  async getAuditLogs(limit = 50, offset = 0) {
    return await this.request(`/api/v1/security/audit-logs?limit=${limit}&offset=${offset}`);
  }

  async scanCode(code) {
    return await this.request("/api/v1/security/scan-code", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
  }

  // --- Autonomous Multi-Agent Endpoints ---

  async listAgents() {
    return await this.request("/api/v1/agents");
  }

  async executeAgent(agentName, task, conversationId = null) {
    return await this.request(`/api/v1/agents/${agentName}/execute`, {
      method: "POST",
      body: JSON.stringify({ task, conversation_id: conversationId }),
    });
  }

  async routeAgentTask(query, intent = "general", conversationId = null) {
    return await this.request("/api/v1/agents/route", {
      method: "POST",
      body: JSON.stringify({ query, intent, conversation_id: conversationId }),
    });
  }
}

// Export singleton instance
window.api = new ApiClient();
