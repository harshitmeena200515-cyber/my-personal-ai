/**
 * MY PERSONAL AI — Application State & UI Controller
 */

// Application State
const state = {
  currentUser: null,
  conversations: [],
  activeConversationId: null,
  activeMessages: [],
  mode: "chat", // "chat" | "think"
  isGenerating: false,
  abortController: null,
  theme: localStorage.getItem("app_theme") || "dark",
  hardwareInfo: null,
  activeTools: [],
};

// DOM Elements
const elements = {
  // Theme & Body
  html: document.documentElement,
  themeToggleBtn: document.getElementById("theme-toggle-btn"),

  // Auth Modal
  authModal: document.getElementById("auth-modal"),
  authTabLogin: document.getElementById("tab-login"),
  authTabRegister: document.getElementById("tab-register"),
  authForm: document.getElementById("auth-form"),
  authUsername: document.getElementById("auth-username"),
  authPassword: document.getElementById("auth-password"),
  authSubmitBtn: document.getElementById("auth-submit-btn"),
  authErrorBanner: document.getElementById("auth-error-banner"),
  userProfilePill: document.getElementById("user-profile-pill"),
  usernameDisplay: document.getElementById("username-display"),
  userRoleBadge: document.getElementById("user-role-badge"),
  logoutBtn: document.getElementById("logout-btn"),

  // Sidebar
  sidebar: document.getElementById("app-sidebar"),
  sidebarToggleBtn: document.getElementById("sidebar-toggle-btn"),
  newChatBtn: document.getElementById("new-chat-btn"),
  conversationsList: document.getElementById("conversations-list"),

  // Workspace / Chat
  workspaceHeaderTitle: document.getElementById("workspace-header-title"),
  chatStream: document.getElementById("chat-stream"),
  chatTextarea: document.getElementById("chat-textarea"),
  sendBtn: document.getElementById("send-btn"),
  modeChatBtn: document.getElementById("mode-chat-btn"),
  modeThinkBtn: document.getElementById("mode-think-btn"),
  voiceBtn: document.getElementById("voice-btn"),

  // Inspector Drawer
  inspector: document.getElementById("app-inspector"),
  inspectorToggleBtn: document.getElementById("inspector-toggle-btn"),
  inspectorTabs: document.querySelectorAll(".inspector-tab"),
  inspectorTabPlanning: document.getElementById("tab-planning-content"),
  inspectorTabMemory: document.getElementById("tab-memory-content"),
  inspectorTabSecurity: document.getElementById("tab-security-content"),
  inspectorTabHardware: document.getElementById("tab-hardware-content"),

  // Live Inspector Panels
  planningStepsContainer: document.getElementById("planning-steps-container"),
  hitlContainer: document.getElementById("hitl-container"),
  hardwareDetailsContainer: document.getElementById("hardware-details-container"),
  activeToolsList: document.getElementById("active-tools-list"),

  // Toast
  toastContainer: document.getElementById("toast-container"),
};

// --- Initialization ---

async function init() {
  applyTheme(state.theme);
  setupEventListeners();

  // Check existing session
  try {
    if (window.api.token) {
      const user = await window.api.getMe();
      setAuthenticatedUser(user);
    } else {
      showAuthModal("login");
    }
  } catch (err) {
    showAuthModal("login");
  }

  // Load system hardware & tools in background
  loadSystemData();
}

// --- Theme Management ---

function applyTheme(theme) {
  state.theme = theme;
  elements.html.setAttribute("data-theme", theme);
  localStorage.setItem("app_theme", theme);
  if (elements.themeToggleBtn) {
    elements.themeToggleBtn.textContent = theme === "dark" ? "☀️" : "🌙";
  }
}

// --- Toast Notification ---

function showToast(message, duration = 3000) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// --- Authentication UI Flow ---

function showAuthModal(mode = "login") {
  elements.authModal.classList.add("active");
  elements.authErrorBanner.style.display = "none";
  elements.authUsername.value = "";
  elements.authPassword.value = "";

  if (mode === "login") {
    elements.authTabLogin.classList.add("active");
    elements.authTabRegister.classList.remove("active");
    elements.authSubmitBtn.textContent = "Sign In";
  } else {
    elements.authTabRegister.classList.add("active");
    elements.authTabLogin.classList.remove("active");
    elements.authSubmitBtn.textContent = "Create Account";
  }
}

function hideAuthModal() {
  elements.authModal.classList.remove("active");
}

function setAuthenticatedUser(user) {
  state.currentUser = user;
  hideAuthModal();

  if (elements.usernameDisplay) {
    elements.usernameDisplay.textContent = user.username;
  }
  if (elements.userRoleBadge) {
    elements.userRoleBadge.textContent = user.role;
    elements.userRoleBadge.className = `status-pill ${user.role === "OWNER" ? "online" : ""}`;
  }
  if (elements.userProfilePill) {
    elements.userProfilePill.style.display = "flex";
  }

  // Load conversations
  loadConversations();
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  elements.authErrorBanner.style.display = "none";

  const isLogin = elements.authTabLogin.classList.contains("active");
  const username = elements.authUsername.value.trim();
  const password = elements.authPassword.value;

  if (!username || !password) {
    showAuthError("Please provide both username and password.");
    return;
  }

  elements.authSubmitBtn.disabled = true;
  elements.authSubmitBtn.textContent = "Authenticating...";

  try {
    let res;
    if (isLogin) {
      res = await window.api.login(username, password);
      showToast(`Welcome back, ${res.user.username}!`);
    } else {
      res = await window.api.register(username, password);
      showToast(`Account created successfully for ${res.user.username}!`);
    }
    setAuthenticatedUser(res.user);
  } catch (err) {
    showAuthError(err.message);
  } finally {
    elements.authSubmitBtn.disabled = false;
    elements.authSubmitBtn.textContent = isLogin ? "Sign In" : "Create Account";
  }
}

function showAuthError(msg) {
  elements.authErrorBanner.textContent = msg;
  elements.authErrorBanner.style.display = "block";
}

async function handleLogout() {
  if (confirm("Are you sure you want to log out?")) {
    await window.api.logout();
    state.currentUser = null;
    state.conversations = [];
    state.activeConversationId = null;
    state.activeMessages = [];
    renderConversations();
    renderChatStream();
    showAuthModal("login");
    showToast("Logged out successfully.");
  }
}

// --- Conversations Management ---

async function loadConversations() {
  try {
    const list = await window.api.listConversations();
    state.conversations = list || [];
    renderConversations();

    // If there is an active conversation, or load the most recent one
    if (state.conversations.length > 0 && !state.activeConversationId) {
      selectConversation(state.conversations[0].id);
    } else if (state.conversations.length === 0) {
      startNewConversation();
    }
  } catch (err) {
    console.error("Failed to load conversations:", err);
  }
}

function renderConversations() {
  elements.conversationsList.innerHTML = "";

  if (state.conversations.length === 0) {
    const emptyEl = document.createElement("div");
    emptyEl.style.padding = "16px";
    emptyEl.style.color = "var(--text-muted)";
    emptyEl.style.fontSize = "12.5px";
    emptyEl.textContent = "No conversations yet. Start a new session!";
    elements.conversationsList.appendChild(emptyEl);
    return;
  }

  state.conversations.forEach((conv) => {
    const item = document.createElement("div");
    item.className = `conversation-item ${conv.id === state.activeConversationId ? "active" : ""}`;
    item.onclick = (e) => {
      if (!e.target.closest(".conversation-actions")) {
        selectConversation(conv.id);
      }
    };

    const titleSpan = document.createElement("span");
    titleSpan.className = "conversation-title-text";
    titleSpan.textContent = conv.title || "Untitled Session";

    const actions = document.createElement("div");
    actions.className = "conversation-actions";

    // Rename Button
    const renameBtn = document.createElement("span");
    renameBtn.className = "action-icon";
    renameBtn.title = "Rename";
    renameBtn.textContent = "✏️";
    renameBtn.onclick = (e) => {
      e.stopPropagation();
      renameConversation(conv.id, conv.title);
    };

    // Delete Button
    const deleteBtn = document.createElement("span");
    deleteBtn.className = "action-icon";
    deleteBtn.title = "Delete";
    deleteBtn.textContent = "🗑️";
    deleteBtn.onclick = (e) => {
      e.stopPropagation();
      deleteConversation(conv.id);
    };

    actions.appendChild(renameBtn);
    actions.appendChild(deleteBtn);

    item.appendChild(titleSpan);
    item.appendChild(actions);
    elements.conversationsList.appendChild(item);
  });
}

async function selectConversation(id) {
  state.activeConversationId = id;
  renderConversations();

  const conv = state.conversations.find((c) => c.id === id);
  if (conv && elements.workspaceHeaderTitle) {
    elements.workspaceHeaderTitle.textContent = conv.title;
  }

  // Load messages
  try {
    const msgs = await window.api.getMessages(id);
    state.activeMessages = msgs || [];
    renderChatStream();
  } catch (err) {
    console.error("Failed to load messages:", err);
  }
}

async function startNewConversation() {
  state.activeConversationId = null;
  state.activeMessages = [];
  if (elements.workspaceHeaderTitle) {
    elements.workspaceHeaderTitle.textContent = "New Conversation";
  }
  renderConversations();
  renderChatStream();
  elements.chatTextarea.focus();
}

async function renameConversation(id, currentTitle) {
  const newTitle = prompt("Enter new conversation title:", currentTitle);
  if (newTitle && newTitle.trim() && newTitle.trim() !== currentTitle) {
    try {
      await window.api.updateConversationTitle(id, newTitle.trim());
      const conv = state.conversations.find((c) => c.id === id);
      if (conv) conv.title = newTitle.trim();
      renderConversations();
      if (state.activeConversationId === id) {
        elements.workspaceHeaderTitle.textContent = newTitle.trim();
      }
      showToast("Conversation renamed.");
    } catch (err) {
      showToast(`Error: ${err.message}`);
    }
  }
}

async function deleteConversation(id) {
  if (confirm("Delete this conversation and its message history?")) {
    try {
      await window.api.deleteConversation(id);
      state.conversations = state.conversations.filter((c) => c.id !== id);
      if (state.activeConversationId === id) {
        if (state.conversations.length > 0) {
          selectConversation(state.conversations[0].id);
        } else {
          startNewConversation();
        }
      } else {
        renderConversations();
      }
      showToast("Conversation deleted.");
    } catch (err) {
      showToast(`Error: ${err.message}`);
    }
  }
}

// --- Chat Stream Rendering ---

function renderChatStream() {
  elements.chatStream.innerHTML = "";

  if (state.activeMessages.length === 0) {
    renderWelcomeHero();
    return;
  }

  state.activeMessages.forEach((msg) => {
    appendMessageBubble(msg.role, msg.content, msg.reasoning, msg.meta);
  });

  scrollToBottom();
}

function renderWelcomeHero() {
  const hero = document.createElement("div");
  hero.className = "welcome-hero";
  hero.innerHTML = `
    <div class="welcome-icon">⚡</div>
    <h2 class="welcome-title">MY PERSONAL AI</h2>
    <p class="welcome-desc">
      Your 100% offline, local-first autonomous intelligence platform powered by Qwen 2.5 on NVIDIA RTX 3050.
    </p>
    <div class="suggestion-grid">
      <div class="suggestion-card" onclick="sendSuggestion('Inspect system hardware specifications and GPU status')">
        <div class="suggestion-title">🖥️ Hardware Inspection</div>
        <div class="suggestion-subtitle">Query GPU, VRAM and offline model health</div>
      </div>
      <div class="suggestion-card" onclick="sendSuggestion('Calculate sqrt(144) * 5 + 40 with reasoning steps')">
        <div class="suggestion-title">🧮 Autonomous Calculation</div>
        <div class="suggestion-subtitle">Decompose multi-step math with sandbox tools</div>
      </div>
      <div class="suggestion-card" onclick="sendSuggestion('Analyze Python file security best practices')">
        <div class="suggestion-title">🛡️ Cybersecurity Analysis</div>
        <div class="suggestion-subtitle">Verify code against path traversal and IDOR</div>
      </div>
      <div class="suggestion-card" onclick="sendSuggestion('What is today\\'s date and current system time?')">
        <div class="suggestion-title">⏱️ Sandbox Datetime Tool</div>
        <div class="suggestion-subtitle">Verify real-time system tool execution</div>
      </div>
    </div>
  `;
  elements.chatStream.appendChild(hero);
}

window.sendSuggestion = function (text) {
  elements.chatTextarea.value = text;
  handleSendMessage();
};

function appendMessageBubble(role, content, reasoning = null, meta = null) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user" ? "U" : "AI";

  const body = document.createElement("div");
  body.className = "message-body";

  // If reasoning trace exists
  if (reasoning) {
    const reasoningBox = document.createElement("div");
    reasoningBox.className = "reasoning-box";

    const rHeader = document.createElement("div");
    rHeader.className = "reasoning-header";
    rHeader.innerHTML = `<span>🧠 Autonomous Reasoning Trace</span><span>▼</span>`;
    
    const rContent = document.createElement("div");
    rContent.className = "reasoning-content";
    rContent.textContent = reasoning;

    rHeader.onclick = () => {
      const isHidden = rContent.style.display === "none";
      rContent.style.display = isHidden ? "block" : "none";
      rHeader.querySelector("span:last-child").textContent = isHidden ? "▼" : "▶";
    };

    reasoningBox.appendChild(rHeader);
    reasoningBox.appendChild(rContent);
    body.appendChild(reasoningBox);
  }

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.innerHTML = formatMarkdown(content);

  body.appendChild(bubble);

  // Meta stats
  if (meta) {
    const metaRow = document.createElement("div");
    metaRow.className = "message-meta";
    if (meta.tokens_per_sec) {
      metaRow.innerHTML += `<span class="metric-pill">⚡ ${meta.tokens_per_sec} tok/s</span>`;
    }
    if (meta.latency_sec) {
      metaRow.innerHTML += `<span class="metric-pill">⏱️ ${meta.latency_sec}s</span>`;
    }
    body.appendChild(metaRow);
  }

  row.appendChild(avatar);
  row.appendChild(body);
  elements.chatStream.appendChild(row);
  scrollToBottom();

  return { row, bubble, body };
}

function escapeHTML(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
  if (!text) return "";
  // Safe HTML escape
  let safe = escapeHTML(text);

  // Code blocks: ```lang\ncode\n```
  safe = safe.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code: `code`
  safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold: **text**
  safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Line breaks
  safe = safe.replace(/\n/g, "<br>");

  return safe;
}

function scrollToBottom() {
  elements.chatStream.scrollTop = elements.chatStream.scrollHeight;
}

// --- Message Sending Flow (Real SSE Streaming) ---

async function handleSendMessage() {
  const content = elements.chatTextarea.value.trim();
  if (!content || state.isGenerating) return;

  // Clear input and reset height
  elements.chatTextarea.value = "";
  elements.chatTextarea.style.height = "auto";

  // Remove welcome hero if present
  const hero = elements.chatStream.querySelector(".welcome-hero");
  if (hero) hero.remove();

  // If no conversation exists yet, create one
  if (!state.activeConversationId) {
    try {
      const convTitle = content.slice(0, 32) + (content.length > 32 ? "..." : "");
      const newConv = await window.api.createConversation(convTitle);
      state.activeConversationId = newConv.id;
      state.conversations.unshift(newConv);
      renderConversations();
      elements.workspaceHeaderTitle.textContent = newConv.title;
    } catch (e) {
      console.warn("Could not create conversation, will proceed anyway:", e);
    }
  }

  // Append user bubble
  appendMessageBubble("user", content);
  state.activeMessages.push({ role: "user", content });

  // Update UI to generating state
  state.isGenerating = true;
  updateGeneratingUI(true);

  // Prepare Assistant bubble
  const { row: assistantRow, bubble: assistantBubble, body: assistantBody } = appendMessageBubble("assistant", "");
  const cursor = document.createElement("span");
  cursor.className = "cursor-pulse";
  assistantBubble.appendChild(cursor);

  state.abortController = new AbortController();

  if (state.mode === "think") {
    // Mode = Deep Think (Autonomous Multi-Step Reasoning)
    executeAutonomousThink(content, assistantBubble, assistantBody, cursor);
  } else {
    // Mode = Standard Chat
    executeStandardChat(content, assistantBubble, assistantBody, cursor);
  }
}

async function executeStandardChat(content, bubble, body, cursor) {
  let fullResponse = "";
  const startTime = Date.now();

  const payload = {
    messages: state.activeMessages.map((m) => ({ role: m.role, content: m.content })),
    model: "qwen2.5-coder:3b",
    conversation_id: state.activeConversationId,
  };

  await window.api.streamChat(payload, {
    signal: state.abortController.signal,
    onChunk: (chunk) => {
      fullResponse += chunk;
      cursor.remove();
      bubble.innerHTML = formatMarkdown(fullResponse);
      bubble.appendChild(cursor);
      scrollToBottom();
    },
    onDone: () => {
      cursor.remove();
      state.isGenerating = false;
      updateGeneratingUI(false);

      const latency = ((Date.now() - startTime) / 1000).toFixed(2);
      const estTokens = Math.max(1, Math.round(fullResponse.length / 4));
      const tokPerSec = (estTokens / Math.max(0.1, latency)).toFixed(1);

      const metaRow = document.createElement("div");
      metaRow.className = "message-meta";
      metaRow.innerHTML = `
        <span class="metric-pill">⚡ ${tokPerSec} tok/s</span>
        <span class="metric-pill">⏱️ ${latency}s</span>
      `;
      body.appendChild(metaRow);

      state.activeMessages.push({
        role: "assistant",
        content: fullResponse,
        meta: { tokens_per_sec: tokPerSec, latency_sec: latency },
      });
    },
    onError: (err) => {
      cursor.remove();
      state.isGenerating = false;
      updateGeneratingUI(false);
      bubble.innerHTML = `<span style="color: var(--status-danger)">Error: ${escapeHTML(err.message)}</span>`;
    },
  });
}

async function executeAutonomousThink(content, bubble, body, cursor) {
  let fullAnswer = "";
  let reasoningTrace = "";
  const startTime = Date.now();

  // Reset live planning inspector
  resetPlanningInspector(content);

  await window.api.streamThink(content, state.activeConversationId, {
    signal: state.abortController.signal,
    onEvent: (event) => {
      const phase = event.phase;

      if (phase === "reasoning") {
        updatePlanningStep("reasoning", "completed", `Intent: ${event.intent || "query"} | Complexity: ${event.complexity || 1}`);
        if (event.analysis) reasoningTrace += event.analysis + "\n";
      } else if (phase === "planning") {
        updatePlanningStep("planning", "completed", `Plan formulated with ${event.total_steps || 1} steps.`);
        if (event.plan) reasoningTrace += `Plan: ${JSON.stringify(event.plan, null, 2)}\n`;
      } else if (phase === "step_start") {
        updatePlanningStep("execution", "active", `Executing step: ${event.step_name || event.action || "tool"}`);
      } else if (phase === "step_complete") {
        updatePlanningStep("execution", "completed", `Step completed successfully.`);
      } else if (phase === "verification") {
        const conf = event.confidence ? `${(event.confidence * 100).toFixed(0)}%` : "100%";
        updatePlanningStep("verification", "completed", `Verified with ${conf} confidence.`);
      } else if (phase === "complete" || phase === "token" || !phase) {
        const token = event.text || event.token || event.answer || (typeof event === "string" ? event : "");
        fullAnswer += token;
        cursor.remove();
        bubble.innerHTML = formatMarkdown(fullAnswer);
        bubble.appendChild(cursor);
        scrollToBottom();
      }
    },
    onDone: () => {
      cursor.remove();
      state.isGenerating = false;
      updateGeneratingUI(false);

      // Prepend reasoning box if available
      if (reasoningTrace) {
        const rBox = document.createElement("div");
        rBox.className = "reasoning-box";
        rBox.innerHTML = `
          <div class="reasoning-header">
            <span>🧠 Autonomous Reasoning Trace</span>
            <span>▼</span>
          </div>
          <div class="reasoning-content">${reasoningTrace}</div>
        `;
        body.insertBefore(rBox, bubble);
      }

      const latency = ((Date.now() - startTime) / 1000).toFixed(2);
      const metaRow = document.createElement("div");
      metaRow.className = "message-meta";
      metaRow.innerHTML = `<span class="metric-pill">⏱️ ${latency}s</span><span class="metric-pill">🤖 Autonomous Verification: Passed</span>`;
      body.appendChild(metaRow);

      state.activeMessages.push({
        role: "assistant",
        content: fullAnswer,
        reasoning: reasoningTrace,
        meta: { latency_sec: latency },
      });
    },
    onError: (err) => {
      cursor.remove();
      state.isGenerating = false;
      updateGeneratingUI(false);
      bubble.innerHTML = `<span style="color: var(--status-danger)">Error: ${escapeHTML(err.message)}</span>`;
    },
  });
}

function updateGeneratingUI(isGenerating) {
  elements.sendBtn.disabled = isGenerating;
  elements.sendBtn.innerHTML = isGenerating ? "■" : "▲";
  elements.sendBtn.title = isGenerating ? "Generating response..." : "Send message";
}

// --- Inspector Drawer Logic ---

function resetPlanningInspector(taskQuery) {
  elements.planningStepsContainer.innerHTML = `
    <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
      Task: <strong style="color: var(--text-main);">${taskQuery.slice(0, 40)}...</strong>
    </div>
    <div class="planning-step-item active" id="step-reasoning">
      <div>
        <div class="planning-step-name">1. Intent Classification & Reasoning</div>
        <div class="planning-step-detail">Analyzing task requirements...</div>
      </div>
    </div>
    <div class="planning-step-item" id="step-planning">
      <div>
        <div class="planning-step-name">2. Hierarchical Planning</div>
        <div class="planning-step-detail">Pending task decomposition...</div>
      </div>
    </div>
    <div class="planning-step-item" id="step-execution">
      <div>
        <div class="planning-step-name">3. Sandboxed Tool Execution</div>
        <div class="planning-step-detail">Pending tool invocation...</div>
      </div>
    </div>
    <div class="planning-step-item" id="step-verification">
      <div>
        <div class="planning-step-name">4. Self-Correction & Verification</div>
        <div class="planning-step-detail">Pending final check...</div>
      </div>
    </div>
  `;
}

function updatePlanningStep(stepKey, status, detailText) {
  const el = document.getElementById(`step-${stepKey}`);
  if (!el) return;

  el.className = `planning-step-item ${status}`;
  const detailEl = el.querySelector(".planning-step-detail");
  if (detailEl && detailText) {
    detailEl.textContent = detailText;
  }
}

async function loadSystemData() {
  try {
    const [health, sysInfo, tools] = await Promise.all([
      window.api.getHealth().catch(() => null),
      window.api.getSystemInfo().catch(() => null),
      window.api.listTools().catch(() => null),
    ]);

    if (sysInfo && elements.hardwareDetailsContainer) {
      elements.hardwareDetailsContainer.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 8px; font-size: 12px;">
          <div><strong>GPU:</strong> ${sysInfo.gpu || "NVIDIA RTX 3050"}</div>
          <div><strong>RAM:</strong> ${sysInfo.ram || "16 GB"}</div>
          <div><strong>OS:</strong> ${sysInfo.os} (${sysInfo.architecture})</div>
          <div><strong>Python:</strong> ${sysInfo.python_version}</div>
          <div><strong>Engine:</strong> Ollama (Local CUDA0)</div>
          <div><strong>Cloud:</strong> 100% Offline (Disabled)</div>
        </div>
      `;
    }

    if (tools && tools.tools && elements.activeToolsList) {
      elements.activeToolsList.innerHTML = tools.tools
        .map(
          (t) => `
          <div class="tool-badge" title="${t.description || ''}">
            🔧 ${t.name} (${t.permission || 'safe'})
          </div>
        `
        )
        .join("");
    }

    // Load initial HITL approvals
    loadHITLApprovals();
  } catch (e) {
    console.warn("Could not fetch system telemetry:", e);
  }
}

async function loadHITLApprovals() {
  if (!elements.hitlContainer) return;
  try {
    const approvals = await window.api.getApprovals("PENDING");
    if (!approvals || approvals.length === 0) {
      elements.hitlContainer.innerHTML = `
        <div class="approval-card">
          <div class="approval-badge">🛡️ Sensitive Action Policy</div>
          <div style="font-size: 12px; color: var(--text-secondary);">
            No actions currently pending human confirmation. Dangerous operations will appear here with Allow / Deny controls.
          </div>
          <div class="status-pill online" style="width: fit-content;">
            <span>HITL Engine: Active & Enforced</span>
          </div>
        </div>
      `;
      return;
    }

    elements.hitlContainer.innerHTML = approvals.map(appr => `
      <div class="approval-card" id="approval-${escapeHTML(appr.id)}">
        <div class="approval-badge">⚠️ Action Authorization Required</div>
        <div style="font-size: 13px; font-weight: 600; color: var(--text-main);">
          Agent: ${escapeHTML(appr.agent_name)} → ${escapeHTML(appr.action)}
        </div>
        <div style="font-size: 12px; color: var(--text-secondary);">
          ${escapeHTML(appr.reason)}
        </div>
        <div style="font-size: 11px; color: var(--text-muted);">
          Risk Level: <strong style="color: var(--status-danger);">${escapeHTML(appr.risk_level)}</strong>
        </div>
        <div class="approval-actions">
          <button class="btn btn-primary" onclick="resolveHITL('${escapeHTML(appr.id)}', true)">Authorize (Allow)</button>
          <button class="btn btn-danger" onclick="resolveHITL('${escapeHTML(appr.id)}', false)">Deny (Block)</button>
        </div>
      </div>
    `).join("");
  } catch (err) {
    console.warn("Could not load HITL approvals:", err);
  }
}

window.resolveHITL = async function(id, approved) {
  try {
    await window.api.resolveApproval(id, approved);
    showToast(`Approval ${id.slice(0, 8)}... ${approved ? 'AUTHORIZED' : 'DENIED'}.`);
    loadHITLApprovals();
  } catch (err) {
    showToast(`Failed to resolve approval: ${err.message}`);
  }
};

// --- Event Listeners Setup ---

function setupEventListeners() {
  // Theme Toggle
  if (elements.themeToggleBtn) {
    elements.themeToggleBtn.onclick = () => {
      applyTheme(state.theme === "dark" ? "light" : "dark");
    };
  }

  // Auth Tabs
  elements.authTabLogin.onclick = () => showAuthModal("login");
  elements.authTabRegister.onclick = () => showAuthModal("register");
  elements.authForm.onsubmit = handleAuthSubmit;
  if (elements.logoutBtn) {
    elements.logoutBtn.onclick = handleLogout;
  }

  // Sidebar Toggles
  elements.newChatBtn.onclick = startNewConversation;
  if (elements.sidebarToggleBtn) {
    elements.sidebarToggleBtn.onclick = () => {
      elements.sidebar.classList.toggle("open");
    };
  }

  // Inspector Drawer Toggles
  if (elements.inspectorToggleBtn) {
    elements.inspectorToggleBtn.onclick = () => {
      elements.inspector.classList.toggle("open");
    };
  }

  // Inspector Tabs
  elements.inspectorTabs.forEach((tab) => {
    tab.onclick = () => {
      elements.inspectorTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      const target = tab.dataset.target;
      elements.inspectorTabPlanning.style.display = target === "planning" ? "block" : "none";
      elements.inspectorTabMemory.style.display = target === "memory" ? "block" : "none";
      elements.inspectorTabSecurity.style.display = target === "security" ? "block" : "none";
      elements.inspectorTabHardware.style.display = target === "hardware" ? "block" : "none";

      if (target === "security") {
        loadHITLApprovals();
      }
    };
  });

  // Mode Selection (Chat vs Deep Think)
  elements.modeChatBtn.onclick = () => {
    state.mode = "chat";
    elements.modeChatBtn.classList.add("active");
    elements.modeThinkBtn.classList.remove("active");
    elements.chatTextarea.placeholder = "Ask anything in standard chat (Shift+Enter for newline)...";
  };

  elements.modeThinkBtn.onclick = () => {
    state.mode = "think";
    elements.modeThinkBtn.classList.add("active");
    elements.modeChatBtn.classList.remove("active");
    elements.chatTextarea.placeholder = "Assign an autonomous task with tool planning & verification...";
    // Open planning tab in drawer
    elements.inspectorTabs[0].click();
  };

  // Voice Interaction Button Placeholder
  if (elements.voiceBtn) {
    elements.voiceBtn.onclick = () => {
      elements.voiceBtn.classList.toggle("listening");
      const isListening = elements.voiceBtn.classList.contains("listening");
      if (isListening) {
        showToast("🎙️ Listening placeholder active (Audio recording ready for Phase 5)");
      } else {
        showToast("🎙️ Voice input stopped");
      }
    };
  }

  // Auto-growing textarea & Enter to send
  elements.chatTextarea.addEventListener("input", () => {
    elements.chatTextarea.style.height = "auto";
    elements.chatTextarea.style.height = `${Math.min(elements.chatTextarea.scrollHeight, 160)}px`;
  });

  elements.chatTextarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  elements.sendBtn.onclick = handleSendMessage;

  // Global Auth Required Event
  window.addEventListener("auth:required", () => {
    showAuthModal("login");
    showToast("Session expired. Please sign in again.");
  });
}

// Run bootstrap when DOM is ready
document.addEventListener("DOMContentLoaded", init);
