/**
 * MY PERSONAL AI — Neo-Intelligence Command Center Controller
 * Complete voice recognition (STT), voice synthesis (TTS), math formatting,
 * model cascading, and multi-agent telemetry orchestration.
 */

// Application State
const state = {
  currentUser: null,
  conversations: [],
  activeConversationId: null,
  activeMessages: [],
  selectedModel: "gemini-flash-lite-latest",
  isGenerating: false,
  autoSpeak: false,
  isListening: false,
  speechRecognition: null,
  currentSpeakingUtterance: null,
};

// DOM Elements
const elements = {
  // Theme & Model
  html: document.documentElement,
  themeToggleBtn: document.getElementById("theme-toggle-btn"),
  headerModelSelect: document.getElementById("header-model-select"),
  activeModelIndicator: document.getElementById("active-model-indicator"),

  // Voice TTS & Mic STT
  voiceTtsToggle: document.getElementById("voice-tts-toggle"),
  ttsIcon: document.getElementById("tts-icon"),
  ttsLabel: document.getElementById("tts-label"),
  voiceBtn: document.getElementById("voice-btn"),
  voiceMicIcon: document.getElementById("voice-mic-icon"),
  recordingStatusText: document.getElementById("recording-status-text"),

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

  // Sidebar & Modules
  sidebar: document.getElementById("app-sidebar"),
  sidebarToggleBtn: document.getElementById("sidebar-toggle-btn"),
  newChatBtn: document.getElementById("new-chat-btn"),
  conversationsList: document.getElementById("conversations-list"),
  moduleNavItems: document.querySelectorAll(".module-nav-item"),

  // Workspace
  workspaceHeaderTitle: document.getElementById("workspace-header-title"),
  clearChatBtn: document.getElementById("clear-chat-btn"),
  chatStream: document.getElementById("chat-stream"),
  chatTextarea: document.getElementById("chat-textarea"),
  sendBtn: document.getElementById("send-btn"),

  // Right Inspector
  inspector: document.getElementById("app-inspector"),
  inspectorToggleBtn: document.getElementById("inspector-toggle-btn"),
  inspectorTabBtns: document.querySelectorAll(".inspector-tab-btn"),
  inspectorPanels: {
    agents: document.getElementById("tab-panel-agents"),
    cavp: document.getElementById("tab-panel-cavp"),
    memory: document.getElementById("tab-panel-memory"),
    hardware: document.getElementById("tab-panel-hardware"),
  },

  // Toast
  toastContainer: document.getElementById("toast-container"),
};

// ============================================================================
// 1. Initialization
// ============================================================================

async function init() {
  setupEventListeners();
  initVoiceSystem();

  // Expose starter prompt to window
  window.useStarterPrompt = useStarterPrompt;

  // Check saved theme
  const savedTheme = localStorage.getItem("app_theme") || "dark";
  applyTheme(savedTheme);

  // Auto-authenticate as primary owner on local machine
  try {
    let user = null;
    if (window.api.token) {
      try {
        user = await window.api.getMe();
      } catch (e) {
        window.api.setToken(null);
      }
    }

    if (!user) {
      const loginRes = await window.api.login("harshit", "Harshit@123");
      user = loginRes.user;
    }

    setAuthenticatedUser(user);
  } catch (err) {
    console.warn("Auto-login error:", err);
    showAuthModal("login");
  }
}

// ============================================================================
// 2. Authentication Management
// ============================================================================

function showAuthModal(mode = "login") {
  elements.authModal.classList.add("active", "visible");
  elements.authErrorBanner.style.display = "none";
  if (mode === "login") {
    elements.authTabLogin.classList.add("active");
    elements.authTabRegister.classList.remove("active");
    elements.authSubmitBtn.textContent = "Access Command Center";
  } else {
    elements.authTabRegister.classList.add("active");
    elements.authTabLogin.classList.remove("active");
    elements.authSubmitBtn.textContent = "Create Account";
  }
}

function hideAuthModal() {
  elements.authModal.classList.remove("active", "visible");
}

function setAuthenticatedUser(user) {
  state.currentUser = user;
  hideAuthModal();
  if (elements.userProfilePill) {
    elements.userProfilePill.style.display = "flex";
    elements.usernameDisplay.textContent = user.username;
    elements.userRoleBadge.textContent = user.role || "USER";
  }
  loadConversations();
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const username = elements.authUsername.value.trim();
  const password = elements.authPassword.value;
  const isRegister = elements.authTabRegister.classList.contains("active");

  elements.authErrorBanner.style.display = "none";
  elements.authSubmitBtn.disabled = true;

  try {
    if (isRegister) {
      await window.api.register(username, password);
      showToast("Account created successfully. Logging in...");
    }
    const loginRes = await window.api.login(username, password);
    setAuthenticatedUser(loginRes.user);
    showToast(`Welcome back, ${loginRes.user.username}!`);
  } catch (err) {
    elements.authErrorBanner.textContent = err.message || "Authentication failed.";
    elements.authErrorBanner.style.display = "block";
  } finally {
    elements.authSubmitBtn.disabled = false;
  }
}

async function handleLogout() {
  if (confirm("Sign out of Personal AI Command Center?")) {
    await window.api.logout();
    state.currentUser = null;
    state.conversations = [];
    state.activeConversationId = null;
    state.activeMessages = [];
    renderConversations();
    renderChatStream();
    showAuthModal("login");
    showToast("Signed out.");
  }
}

// ============================================================================
// 3. Voice Interaction System (Speech-to-Text & Text-to-Speech)
// ============================================================================

function initVoiceSystem() {
  // Speech Recognition (STT)
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRec) {
    state.speechRecognition = new SpeechRec();
    state.speechRecognition.continuous = false;
    state.speechRecognition.interimResults = true;
    state.speechRecognition.lang = "hi-IN"; // Supports Hindi & English naturally

    state.speechRecognition.onstart = () => {
      state.isListening = true;
      elements.voiceBtn.classList.add("listening");
      elements.voiceMicIcon.textContent = "🔴";
      elements.recordingStatusText.style.display = "inline";
    };

    state.speechRecognition.onresult = (e) => {
      let transcript = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript;
      }
      elements.chatTextarea.value = transcript;
      autoResizeTextarea();
    };

    state.speechRecognition.onerror = (e) => {
      console.warn("Speech recognition error:", e.error);
      stopListening();
    };

    state.speechRecognition.onend = () => {
      stopListening();
      // If text captured, focus textarea
      if (elements.chatTextarea.value.trim().length > 0) {
        elements.chatTextarea.focus();
      }
    };
  }

  // Voice TTS Toggle Button
  if (elements.voiceTtsToggle) {
    elements.voiceTtsToggle.onclick = () => {
      state.autoSpeak = !state.autoSpeak;
      elements.voiceTtsToggle.classList.toggle("enabled", state.autoSpeak);
      elements.ttsIcon.textContent = state.autoSpeak ? "🔊" : "🔈";
      elements.ttsLabel.textContent = state.autoSpeak ? "Voice Reply: ON" : "Voice Reply: Off";
      showToast(state.autoSpeak ? "🔊 Automatic voice speech enabled!" : "🔈 Voice speech disabled.");
    };
  }
}

function toggleListening() {
  if (!state.speechRecognition) {
    alert("Speech recognition is not supported in this browser. Please use Microsoft Edge or Google Chrome.");
    return;
  }

  if (state.isListening) {
    state.speechRecognition.stop();
  } else {
    try {
      state.speechRecognition.start();
    } catch (err) {
      console.error(err);
    }
  }
}

function stopListening() {
  state.isListening = false;
  elements.voiceBtn.classList.remove("listening");
  elements.voiceMicIcon.textContent = "🎙️";
  elements.recordingStatusText.style.display = "none";
}

function speakText(text, btnElement = null) {
  if (!("speechSynthesis" in window)) return;

  // If already speaking, cancel
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
    if (btnElement) btnElement.classList.remove("speaking");
    return;
  }

  // Clean markdown for spoken audio
  const cleanSpoken = text
    .replace(/[#*_`$]/g, "")
    .replace(/\[.*?\]\(.*?\)/g, "")
    .replace(/```[\s\S]*?```/g, "Code block omitted.")
    .replace(/\$\$.*?\$\$/g, "formula")
    .trim();

  const utterance = new SpeechSynthesisUtterance(cleanSpoken);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  // Prefer Indian or standard English / Hindi voice
  const voices = window.speechSynthesis.getVoices();
  const preferredVoice = voices.find((v) => v.lang.includes("IN") || v.lang.includes("hi") || v.lang.includes("en-US"));
  if (preferredVoice) utterance.voice = preferredVoice;

  if (btnElement) {
    btnElement.classList.add("speaking");
    utterance.onend = () => btnElement.classList.remove("speaking");
    utterance.onerror = () => btnElement.classList.remove("speaking");
  }

  window.speechSynthesis.speak(utterance);
}

// ============================================================================
// 4. Conversation & Chat Stream
// ============================================================================

async function loadConversations() {
  try {
    const list = await window.api.listConversations();
    state.conversations = list || [];
    renderConversations();

    if (state.conversations.length > 0 && !state.activeConversationId) {
      selectConversation(state.conversations[0].id);
    } else if (state.conversations.length === 0) {
      startNewConversation();
    }
  } catch (err) {
    console.error("Failed to load sessions:", err);
  }
}

function renderConversations() {
  elements.conversationsList.innerHTML = "";

  if (state.conversations.length === 0) {
    const emptyEl = document.createElement("div");
    emptyEl.style.padding = "12px 14px";
    emptyEl.style.color = "var(--text-muted)";
    emptyEl.style.fontSize = "12px";
    emptyEl.textContent = "No active sessions. Start a new one!";
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
    titleSpan.style.overflow = "hidden";
    titleSpan.style.textOverflow = "ellipsis";
    titleSpan.style.whiteSpace = "nowrap";
    titleSpan.textContent = conv.title || "Untitled Session";

    const actions = document.createElement("div");
    actions.className = "conversation-actions";

    const delBtn = document.createElement("span");
    delBtn.style.cursor = "pointer";
    delBtn.textContent = "🗑️";
    delBtn.title = "Delete Session";
    delBtn.onclick = (e) => {
      e.stopPropagation();
      deleteConversation(conv.id);
    };

    actions.appendChild(delBtn);
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

  try {
    const messages = await window.api.getMessages(id);
    state.activeMessages = messages || [];
    renderChatStream();
  } catch (err) {
    console.error("Failed to load messages:", err);
  }
}

async function startNewConversation() {
  try {
    const conv = await window.api.createConversation("New Intelligence Session");
    state.conversations.unshift(conv);
    state.activeConversationId = conv.id;
    state.activeMessages = [];
    renderConversations();
    renderChatStream();
  } catch (err) {
    console.error("Create session failed:", err);
  }
}

async function deleteConversation(id) {
  if (confirm("Delete this session?")) {
    try {
      await window.api.deleteConversation(id);
      state.conversations = state.conversations.filter((c) => c.id !== id);
      if (state.activeConversationId === id) {
        state.activeConversationId = null;
        state.activeMessages = [];
      }
      renderConversations();
      renderChatStream();
      if (state.conversations.length > 0) {
        selectConversation(state.conversations[0].id);
      } else {
        startNewConversation();
      }
    } catch (err) {
      showToast("Delete failed: " + err.message);
    }
  }
}

// ============================================================================
// 5. Chat Stream Rendering & Markdown / Math Formatting
// ============================================================================

function renderChatStream() {
  elements.chatStream.innerHTML = "";

  if (state.activeMessages.length === 0) {
    // Render Empty State Hero with 4 Starter Cards
    elements.chatStream.innerHTML = `
      <div class="hero-empty-state">
        <div class="neural-orb-wrapper">
          <div class="orbital-ring"></div>
          <div class="orbital-ring reverse"></div>
          <div class="neural-orb">⚡</div>
        </div>
        <h2 class="hero-title">MY PERSONAL AI COMMAND CENTER</h2>
        <p class="hero-subtitle">
          Autonomous intelligence powered by Google AI Studio and RTX 3050.
          Solve complex math, synthesize software, and coordinate multi-agent workflows.
        </p>

        <div class="starter-cards-grid">
          <div class="starter-card" onclick="useStarterPrompt('Solve this math problem step by step: (25 * 14) + sqrt(576) - (120 / 6)')">
            <div class="starter-card-icon">🧮</div>
            <div class="starter-card-title">Solve Complex Math</div>
            <div class="starter-card-desc">PEMDAS, algebra, calculus, and step-by-step arithmetic.</div>
          </div>

          <div class="starter-card" onclick="useStarterPrompt('Perform a deep architectural analysis of our autonomous personal AI platform.')">
            <div class="starter-card-icon">🔍</div>
            <div class="starter-card-title">Google AI Deep Reasoning</div>
            <div class="starter-card-desc">Analyze system architecture and complex logic with Gemini.</div>
          </div>

          <div class="starter-card" onclick="useStarterPrompt('Write a clean, optimized Python asynchronous worker using asyncio and dataclasses.')">
            <div class="starter-card-icon">💻</div>
            <div class="starter-card-title">Code Architecture</div>
            <div class="starter-card-desc">Production Python code, algorithms, and APIs.</div>
          </div>

          <div class="starter-card" onclick="useStarterPrompt('Perform a zero-trust security audit of active DPAPI encryption and process sandboxes.')">
            <div class="starter-card-icon">🛡️</div>
            <div class="starter-card-title">Zero-Trust Security Scan</div>
            <div class="starter-card-desc">Audit Windows memory, Job Objects, and permissions.</div>
          </div>
        </div>
      </div>
    `;
    return;
  }

  state.activeMessages.forEach((msg) => {
    appendMessageElement(msg.role, msg.content, false);
  });

  scrollChatToBottom();
}

function appendMessageElement(role, content, shouldScroll = true) {
  const isUser = role === "user";
  const row = document.createElement("div");
  row.className = `chat-message-row ${isUser ? "user-row" : "assistant-row"}`;

  // Avatar
  const avatar = document.createElement("div");
  avatar.className = `avatar-badge ${isUser ? "user-avatar" : "ai-avatar"}`;
  avatar.textContent = isUser ? "👤" : "⚡";

  // Content Wrapper
  const contentWrapper = document.createElement("div");
  contentWrapper.className = "message-content-wrapper";

  // Bubble
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.innerHTML = formatMessageContent(content);

  contentWrapper.appendChild(bubble);

  // Assistant Action Bar (Speak Button, Model Tag)
  if (!isUser) {
    const actionBar = document.createElement("div");
    actionBar.className = "message-actions-bar";

    const speakBtn = document.createElement("button");
    speakBtn.className = "btn-message-action";
    speakBtn.innerHTML = "<span>🔊</span><span>Listen</span>";
    speakBtn.onclick = () => speakText(content, speakBtn);

    const copyBtn = document.createElement("button");
    copyBtn.className = "btn-message-action";
    copyBtn.innerHTML = "<span>📋</span><span>Copy</span>";
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(content);
      showToast("Copied to clipboard!");
    };

    actionBar.appendChild(speakBtn);
    actionBar.appendChild(copyBtn);
    contentWrapper.appendChild(actionBar);
  }

  if (isUser) {
    row.appendChild(contentWrapper);
    row.appendChild(avatar);
  } else {
    row.appendChild(avatar);
    row.appendChild(contentWrapper);
  }

  elements.chatStream.appendChild(row);

  if (shouldScroll) {
    scrollChatToBottom();
  }

  return bubble;
}

function formatMessageContent(rawText) {
  if (!rawText) return "";

  let formatted = rawText;

  // 1. Math block formatting ($$ ... $$)
  formatted = formatted.replace(/\$\$([\s\S]*?)\$\$/g, (match, formula) => {
    return `<div class="math-formula-box">📐 ${escapeHtml(formula.trim())}</div>`;
  });

  // 2. Code blocks (```language ... ```)
  formatted = formatted.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const safeLang = lang || "code";
    const safeCode = escapeHtml(code.trim());
    return `
      <div class="code-block-container">
        <div class="code-block-header">
          <span>${safeLang.toUpperCase()}</span>
          <button class="btn-copy-code" onclick="navigator.clipboard.writeText(decodeURIComponent('${encodeURIComponent(code.trim())}')); showToast('Code copied!');">Copy</button>
        </div>
        <pre class="code-block-pre"><code>${safeCode}</code></pre>
      </div>
    `;
  });

  // 3. Inline code (`code`)
  formatted = formatted.replace(/`([^`]+)`/g, '<code style="background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 12.5px; color: #38bdf8;">$1</code>');

  // 4. Headers & Bold
  formatted = formatted.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  formatted = formatted.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  formatted = formatted.replace(/^# (.*$)/gim, '<h1>$1</h1>');
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // 5. Line breaks to paragraphs
  const paragraphs = formatted.split("\n\n").filter((p) => p.trim().length > 0);
  if (paragraphs.length > 1) {
    formatted = paragraphs.map((p) => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
  } else {
    formatted = `<p>${formatted.replace(/\n/g, "<br>")}</p>`;
  }

  return formatted;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function scrollChatToBottom() {
  elements.chatStream.scrollTop = elements.chatStream.scrollHeight;
}

function useStarterPrompt(prompt) {
  elements.chatTextarea.value = prompt;
  autoResizeTextarea();
  sendMessage();
}

// ============================================================================
// 6. Sending Messages & Autonomous Response
// ============================================================================

async function sendMessage() {
  const text = elements.chatTextarea.value.trim();
  if (!text || state.isGenerating) return;

  // Auto-create session if none active
  if (!state.activeConversationId) {
    try {
      const conv = await window.api.createConversation("New Intelligence Session");
      state.conversations.unshift(conv);
      state.activeConversationId = conv.id;
      renderConversations();
    } catch (e) {
      console.warn("Auto-create conv failed:", e);
    }
  }

  // Clear input
  elements.chatTextarea.value = "";
  autoResizeTextarea();
  state.isGenerating = true;
  elements.sendBtn.disabled = true;

  // Append user message
  appendMessageElement("user", text);

  // Create active bubble for assistant
  const assistantBubble = appendMessageElement("assistant", "Thinking...");

  try {
    const selectedModel = elements.headerModelSelect ? elements.headerModelSelect.value : "gemini-flash-lite-latest";

    // Persist user message to conversation history
    if (state.activeConversationId) {
      try {
        await window.api.addMessage(state.activeConversationId, "user", text);
      } catch (e) {
        console.warn("Save user msg error:", e);
      }
    }

    // Call unified chat router (supports Gemini + Ollama)
    const chatReq = {
      messages: [{ role: "user", content: text }],
      model: selectedModel,
      stream: false,
    };

    const response = await window.api.sendChat(chatReq);
    const replyContent = response.content || response.answer || "Computation complete.";

    // Persist assistant reply
    if (state.activeConversationId) {
      try {
        await window.api.addMessage(state.activeConversationId, "assistant", replyContent);
      } catch (e) {
        console.warn("Save assistant msg error:", e);
      }
    }

    assistantBubble.innerHTML = formatMessageContent(replyContent);
    scrollChatToBottom();

    // Auto-speak if enabled
    if (state.autoSpeak) {
      speakText(replyContent);
    }
  } catch (err) {
    console.error("Message send error:", err);
    assistantBubble.innerHTML = `<span style="color: var(--status-danger);">⚠️ Error: ${escapeHtml(err.message)}</span>`;
  } finally {
    state.isGenerating = false;
    elements.sendBtn.disabled = false;
  }
}

// ============================================================================
// 7. Event Listeners & UI Controls
// ============================================================================

function setupEventListeners() {
  // Sidebar Module Navigation
  elements.moduleNavItems.forEach((item) => {
    item.onclick = (e) => {
      e.preventDefault();
      elements.moduleNavItems.forEach((i) => i.classList.remove("active"));
      item.classList.add("active");

      const view = item.dataset.view;
      if (view === "chat") {
        // Return to Chat Canvas
        showToast("💬 Neural Chat Canvas Active");
      } else if (view === "agents" || view === "cavp" || view === "memory") {
        // Open Right Inspector to matching tab
        if (elements.inspector) elements.inspector.classList.remove("collapsed");
        const targetTab = document.querySelector(`.inspector-tab-btn[data-tab="${view}"]`);
        if (targetTab) targetTab.click();
        showToast(`Opened ${item.innerText.trim()} Panel`);
      } else if (view === "models") {
        if (elements.headerModelSelect) {
          elements.headerModelSelect.focus();
          showToast("🔮 Model Engine Selected (Google AI Studio / Local)");
        }
      } else if (view === "security") {
        if (elements.inspector) elements.inspector.classList.remove("collapsed");
        const targetTab = document.querySelector(`.inspector-tab-btn[data-tab="cavp"]`);
        if (targetTab) targetTab.click();
        showToast("🔒 Zero-Trust Security & DPAPI Enforced");
      } else {
        showToast(`⚡ ${item.innerText.trim()} Module Active`);
      }
    };
  });

  // Theme Toggle
  if (elements.themeToggleBtn) {
    elements.themeToggleBtn.onclick = () => {
      const nextTheme = elements.html.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(nextTheme);
    };
  }

  // Model Selection
  if (elements.headerModelSelect) {
    elements.headerModelSelect.onchange = (e) => {
      state.selectedModel = e.target.value;
      if (elements.activeModelIndicator) {
        const selectedText = e.target.options[e.target.selectedIndex].text;
        elements.activeModelIndicator.textContent = "Model: " + selectedText.split("(")[0].trim();
      }
      showToast(`Switched model to ${state.selectedModel}`);
    };
  }

  // Textarea Auto-Resize & Enter key to send
  if (elements.chatTextarea) {
    elements.chatTextarea.oninput = autoResizeTextarea;
    elements.chatTextarea.onkeydown = (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    };
  }

  // Send Button
  if (elements.sendBtn) {
    elements.sendBtn.onclick = sendMessage;
  }

  // Microphone Voice Button
  if (elements.voiceBtn) {
    elements.voiceBtn.onclick = toggleListening;
  }

  // New Chat Button
  if (elements.newChatBtn) {
    elements.newChatBtn.onclick = startNewConversation;
  }

  // Clear Chat Button
  if (elements.clearChatBtn) {
    elements.clearChatBtn.onclick = () => {
      if (confirm("Clear messages in this session?")) {
        state.activeMessages = [];
        renderChatStream();
      }
    };
  }

  // Sidebar Toggle
  if (elements.sidebarToggleBtn && elements.sidebar) {
    elements.sidebarToggleBtn.onclick = () => {
      elements.sidebar.classList.toggle("collapsed");
    };
  }

  // Inspector Toggle
  if (elements.inspectorToggleBtn && elements.inspector) {
    elements.inspectorToggleBtn.onclick = () => {
      elements.inspector.classList.toggle("collapsed");
    };
  }

  // Inspector Tabs
  elements.inspectorTabBtns.forEach((btn) => {
    btn.onclick = () => {
      elements.inspectorTabBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tabName = btn.dataset.tab;
      Object.entries(elements.inspectorPanels).forEach(([key, panel]) => {
        if (panel) {
          panel.style.display = key === tabName ? "block" : "none";
        }
      });
    };
  });

  // Auth Form
  if (elements.authForm) {
    elements.authForm.onsubmit = handleAuthSubmit;
  }

  if (elements.authTabLogin) {
    elements.authTabLogin.onclick = () => showAuthModal("login");
  }

  if (elements.authTabRegister) {
    elements.authTabRegister.onclick = () => showAuthModal("register");
  }

  if (elements.logoutBtn) {
    elements.logoutBtn.onclick = handleLogout;
  }
}

function autoResizeTextarea() {
  const ta = elements.chatTextarea;
  if (!ta) return;
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 180) + "px";
}

function applyTheme(theme) {
  elements.html.setAttribute("data-theme", theme);
  localStorage.setItem("app_theme", theme);
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  toast.style.background = "rgba(15, 23, 42, 0.95)";
  toast.style.backdropFilter = "blur(12px)";
  toast.style.border = "1px solid var(--border-neon)";
  toast.style.color = "#f8fafc";
  toast.style.padding = "10px 18px";
  toast.style.borderRadius = "var(--radius-md)";
  toast.style.fontSize = "13px";
  toast.style.boxShadow = "0 8px 24px rgba(0,0,0,0.5)";
  toast.style.marginTop = "8px";
  toast.style.animation = "fadeIn 0.2s ease-out";

  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 250);
  }, 2800);
}

// Run Initialization on DOM Ready
document.addEventListener("DOMContentLoaded", init);
