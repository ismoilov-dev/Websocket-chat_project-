/*
 * static/js/chat.js
 *
 * Frontend mantiq. Ikki xil aloqa ishlatiladi:
 *   1) HTTP (fetch)   - bir martalik ma'lumot: userlar ro'yxati, chat tarixi
 *   2) WebSocket      - real-time: yangi xabar, typing, online status, read status
 */
(() => {
  "use strict";

  // ------------------------------------------------------------------
  // Holat (state)
  // ------------------------------------------------------------------
  const currentUserId = JSON.parse(document.getElementById("current-user-id").textContent);
  const WS_SCHEME = window.location.protocol === "https:" ? "wss" : "ws";

  const state = {
    users: new Map(),     // id -> user obyekt
    activeUserId: null,   // hozir ochiq chat
    chatSocket: null,
    presenceSocket: null,
  };

  // ------------------------------------------------------------------
  // DOM elementlar
  // ------------------------------------------------------------------
  const el = {
    userList: document.getElementById("user-list"),
    chatEmpty: document.getElementById("chat-empty"),
    chatBox: document.getElementById("chat-box"),
    chatTitle: document.getElementById("chat-title"),
    chatStatus: document.getElementById("chat-status"),
    connState: document.getElementById("connection-state"),
    messages: document.getElementById("messages"),
    typing: document.getElementById("typing-indicator"),
    form: document.getElementById("message-form"),
    input: document.getElementById("message-input"),
  };

  // ------------------------------------------------------------------
  // Yordamchi funksiyalar
  // ------------------------------------------------------------------
  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : null;
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        // POST/PUT/DELETE uchun Django CSRF token talab qiladi
        "X-CSRFToken": getCookie("csrftoken"),
      },
      ...options,
    });
    if (response.status === 403 || response.status === 401) {
      window.location.href = "/accounts/login/";
      throw new Error("Unauthenticated");
    }
    if (!response.ok) throw new Error(`API xatosi: ${response.status}`);
    return response.json();
  }

  function formatTime(iso) {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function formatLastSeen(iso) {
    if (!iso) return "offline";
    const d = new Date(iso);
    const sameDay = d.toDateString() === new Date().toDateString();
    return "last seen " + (sameDay ? formatTime(iso) : d.toLocaleString([], { dateStyle: "short", timeStyle: "short" }));
  }

  function scrollToBottom() {
    el.messages.scrollTop = el.messages.scrollHeight;
  }

  // ------------------------------------------------------------------
  // Userlar ro'yxati (sidebar)
  // ------------------------------------------------------------------
  async function loadUsers() {
    const users = await api("/api/users/");
    state.users.clear();
    users.forEach((u) => state.users.set(u.id, u));
    renderUsers();
  }

  function renderUsers() {
    el.userList.innerHTML = "";
    if (state.users.size === 0) {
      el.userList.innerHTML = '<li class="muted" style="padding:16px">Boshqa userlar yo\'q. Yangi user ro\'yxatdan o\'tkazing.</li>';
      return;
    }
    // Online userlar tepada
    const sorted = [...state.users.values()].sort(
      (a, b) => (b.is_online - a.is_online) || a.username.localeCompare(b.username)
    );
    for (const user of sorted) {
      const li = document.createElement("li");
      li.className = "user-item" + (user.id === state.activeUserId ? " active" : "");
      li.dataset.userId = user.id;

      const dot = document.createElement("span");
      dot.className = "dot" + (user.is_online ? " online" : "");
      dot.title = user.is_online ? "online" : "offline";

      const name = document.createElement("span");
      name.className = "name";
      name.textContent = user.full_name; // textContent - XSS'dan himoya

      li.append(dot, name);

      if (user.unread_count > 0) {
        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = user.unread_count;
        li.append(badge);
      }

      li.addEventListener("click", () => openChat(user.id));
      el.userList.append(li);
    }
  }

  function showUsersError() {
    el.userList.innerHTML = '<li class="muted" style="padding:16px">Userlarni yuklab bo\'lmadi.</li>';
  }

  function renderChatStatus() {
    const user = state.users.get(state.activeUserId);
    if (!user) return;
    el.chatStatus.textContent = user.is_online ? "online" : formatLastSeen(user.last_seen);
  }

  // ------------------------------------------------------------------
  // Presence WebSocket: /ws/presence/
  // ------------------------------------------------------------------
  function connectPresence(attempt = 0) {
    const socket = new WebSocket(`${WS_SCHEME}://${window.location.host}/ws/presence/`);
    state.presenceSocket = socket;

    socket.onopen = () => {
      attempt = 0;
      loadUsers(); // qayta ulanganda ham eng so'nggi holatni olamiz
    };

    socket.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "presence") {
        const user = state.users.get(data.user_id);
        if (user) {
          user.is_online = data.is_online;
          user.last_seen = data.last_seen;
          renderUsers();
          if (data.user_id === state.activeUserId) renderChatStatus();
        } else {
          loadUsers(); // yangi ro'yxatdan o'tgan user
        }
      } else if (data.type === "new_message") {
        const senderId = data.message.sender;
        // Agar shu user bilan chat ochiq bo'lmasa -> badge'ni oshiramiz
        if (senderId !== state.activeUserId) {
          const user = state.users.get(senderId);
          if (user) {
            user.unread_count = (user.unread_count || 0) + 1;
            renderUsers();
          } else {
            loadUsers();
          }
        }
      }
    };

    socket.onclose = (e) => {
      if (e.code === 4001) {
        window.location.href = "/accounts/login/";
        return;
      }
      // Tarmoq uzilsa: 1s, 2s, 4s ... 30s gacha kutib qayta ulanamiz
      const delay = Math.min(30000, 1000 * 2 ** attempt);
      setTimeout(() => connectPresence(attempt + 1), delay);
    };
  }

  // ------------------------------------------------------------------
  // Chat WebSocket: /ws/chat/<user_id>/
  // ------------------------------------------------------------------
  async function openChat(userId) {
    if (state.activeUserId === userId && state.chatSocket) return;

    closeChatSocket();
    state.activeUserId = userId;

    const user = state.users.get(userId);
    el.chatEmpty.classList.add("hidden");
    el.chatBox.classList.remove("hidden");
    el.chatTitle.textContent = `Chat with ${user.full_name}`;
    el.typing.classList.add("hidden");
    el.messages.innerHTML = "";
    renderChatStatus();

    user.unread_count = 0;
    renderUsers();

    await loadHistory(userId);
    connectChat(userId);
    el.input.focus();
  }

  async function loadHistory(userId) {
    const messages = await api(`/api/chat/${userId}/messages/`);
    if (state.activeUserId !== userId) return; // bu orada boshqa user tanlangan
    el.messages.innerHTML = "";
    messages.forEach(appendMessage);
    scrollToBottom();
  }

  function connectChat(userId, attempt = 0) {
    const socket = new WebSocket(`${WS_SCHEME}://${window.location.host}/ws/chat/${userId}/`);
    state.chatSocket = socket;

    socket.onopen = () => {
      el.connState.classList.add("connected");
      el.connState.title = "connected";
      markAsRead(); // chat ochildi -> kelgan xabarlarni o'qidik
      if (attempt > 0) loadHistory(userId); // uzilish paytida kelgan xabarlarni olamiz
      attempt = 0;
    };

    socket.onmessage = (e) => handleChatEvent(JSON.parse(e.data));

    socket.onclose = (e) => {
      el.connState.classList.remove("connected");
      el.connState.title = "disconnected";
      if (socket.manuallyClosed || state.activeUserId !== userId) return;
      if (e.code >= 4000) {
        // Server ataylab rad etdi (4001/4003/4004) - qayta urinish befoyda
        showSystemNote(`Ulanish rad etildi (kod ${e.code}).`);
        return;
      }
      const delay = Math.min(30000, 1000 * 2 ** attempt);
      setTimeout(() => {
        if (state.activeUserId === userId) connectChat(userId, attempt + 1);
      }, delay);
    };
  }

  function closeChatSocket() {
    if (state.chatSocket) {
      state.chatSocket.manuallyClosed = true;
      state.chatSocket.close();
      state.chatSocket = null;
    }
    stopTyping();
  }

  function sendWS(payload) {
    const socket = state.chatSocket;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }

  function handleChatEvent(data) {
    switch (data.type) {
      case "chat_message": {
        appendMessage(data.message);
        scrollToBottom();
        if (data.message.sender !== currentUserId) {
          el.typing.classList.add("hidden");
          markAsRead();
        }
        break;
      }
      case "typing": {
        const user = state.users.get(data.user_id);
        el.typing.textContent = `${user ? user.full_name : "User"} is typing...`;
        el.typing.classList.toggle("hidden", !data.is_typing);
        break;
      }
      case "messages_read": {
        // Suhbatdosh mening xabarlarimni o'qidi -> ✓ ni ✓✓ ga almashtiramiz
        if (data.reader_id === currentUserId) break;
        data.message_ids.forEach((id) => {
          const ticks = el.messages.querySelector(`[data-message-id="${id}"] .ticks`);
          if (ticks) {
            ticks.textContent = "✓✓";
            ticks.classList.add("read");
          }
        });
        break;
      }
      case "error":
        showSystemNote(data.detail);
        break;
    }
  }

  function appendMessage(message) {
    const isMine = message.sender === currentUserId;

    const div = document.createElement("div");
    div.className = "message " + (isMine ? "mine" : "theirs");
    div.dataset.messageId = message.id;

    const text = document.createElement("div");
    text.textContent = message.content; // hech qachon innerHTML emas!

    const meta = document.createElement("div");
    meta.className = "meta";
    const time = document.createElement("span");
    time.textContent = formatTime(message.created_at);
    meta.append(time);

    if (isMine) {
      const ticks = document.createElement("span");
      ticks.className = "ticks" + (message.is_read ? " read" : "");
      ticks.textContent = message.is_read ? "✓✓" : "✓";
      ticks.title = message.is_read ? "read" : "sent";
      meta.append(ticks);
    }

    div.append(text, meta);
    el.messages.append(div);
  }

  function showSystemNote(text) {
    const note = document.createElement("div");
    note.className = "typing";
    note.textContent = "⚠ " + text;
    el.messages.append(note);
    scrollToBottom();
  }

  function markAsRead() {
    if (document.visibilityState !== "visible" || !state.activeUserId) return;
    if (!sendWS({ type: "read" })) {
      // Zaxira: WebSocket ochiq bo'lmasa oddiy HTTP POST (CSRF token bilan)
      api(`/api/chat/${state.activeUserId}/read/`, { method: "POST" }).catch(() => {});
    }
  }

  // ------------------------------------------------------------------
  // "User is typing..."
  // ------------------------------------------------------------------
  // Har bir tugma bosilganda xabar yubormaymiz (serverni bosib qo'yadi).
  // Birinchi bosishda "true", 1.5 soniya jimlikdan keyin "false" yuboramiz.
  let typingTimer = null;
  let isTyping = false;

  function onInput() {
    if (!isTyping) {
      isTyping = sendWS({ type: "typing", is_typing: true });
    }
    clearTimeout(typingTimer);
    typingTimer = setTimeout(stopTyping, 1500);
  }

  function stopTyping() {
    clearTimeout(typingTimer);
    if (isTyping) sendWS({ type: "typing", is_typing: false });
    isTyping = false;
  }

  // ------------------------------------------------------------------
  // Event listenerlar
  // ------------------------------------------------------------------
  el.form.addEventListener("submit", (e) => {
    e.preventDefault(); // sahifa refresh bo'lmasin
    const text = el.input.value.trim();
    if (!text) return;
    if (sendWS({ type: "chat_message", message: text })) {
      el.input.value = "";
      stopTyping();
    } else {
      showSystemNote("Server bilan aloqa yo'q. Qayta ulanmoqda...");
    }
  });

  el.input.addEventListener("input", onInput);

  // Tab'ga qaytib kelganda o'qilmagan xabarlarni o'qilgan deb belgilaymiz
  document.addEventListener("visibilitychange", markAsRead);

  // ------------------------------------------------------------------
  // Start
  // ------------------------------------------------------------------
  loadUsers().catch(() => showUsersError());
  connectPresence();
})();
