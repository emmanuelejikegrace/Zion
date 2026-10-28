// ---------- Elements ----------
const loginScreen   = document.getElementById("login-screen");
const signupScreen  = document.getElementById("signup-screen");
const chatScreen    = document.getElementById("chat-screen");

const loginForm     = document.getElementById("login-form");
const loginError    = document.getElementById("login-error");
const loginSubmit   = document.getElementById("login-submit");
const goSignup      = document.getElementById("go-signup");

const signupForm    = document.getElementById("signup-form");
const signupError   = document.getElementById("signup-error");
const signupSubmit  = document.getElementById("signup-submit");
const goLogin       = document.getElementById("go-login");

const whoami        = document.getElementById("whoami");
const logoutBtn     = document.getElementById("logout-btn");
const messagesBox   = document.getElementById("messages");
const messageInput  = document.getElementById("message-input");
const sendBtn       = document.getElementById("send-btn");


// ---------- State ----------
let currentUser = null;
let pollTimer = null;


// ---------- Screen switching ----------
function showScreen(name) {
    loginScreen.classList.add("hidden");
    signupScreen.classList.add("hidden");
    chatScreen.classList.add("hidden");

    if (name === "login") {
        loginScreen.classList.remove("hidden");
        loginError.textContent = "";
    } else if (name === "signup") {
        signupScreen.classList.remove("hidden");
        signupError.textContent = "";
    } else if (name === "chat") {
        chatScreen.classList.remove("hidden");
        whoami.textContent = "@" + currentUser.username;
        loadMessages();
        if (!pollTimer) pollTimer = setInterval(loadMessages, 2000);
    }

    if (name !== "chat" && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}


// ---------- Navigation ----------
goSignup.addEventListener("click", (e) => { e.preventDefault(); showScreen("signup"); });
goLogin.addEventListener("click",  (e) => { e.preventDefault(); showScreen("login");  });


// ---------- Signup ----------
signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    signupError.textContent = "";
    signupSubmit.disabled = true;

    const payload = {
        username: document.getElementById("signup-username").value.trim(),
        password: document.getElementById("signup-password").value,
        confirm_password: document.getElementById("signup-confirm").value,
        security_question: document.getElementById("signup-question").value,
        security_answer: document.getElementById("signup-answer").value,
    };

    try {
        const res = await fetch("/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (!res.ok) {
            signupError.textContent = data.detail || "Signup failed.";
            signupSubmit.disabled = false;
            return;
        }

        // Auto-login after signup
        const loginRes = await fetch("/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: payload.username, password: payload.password }),
        });

        if (!loginRes.ok) {
            signupError.textContent = "Account created, but auto-login failed. Please log in.";
            signupSubmit.disabled = false;
            showScreen("login");
            return;
        }

        await checkAuth();
    } catch (err) {
        console.error(err);
        signupError.textContent = "Network error.";
    } finally {
        signupSubmit.disabled = false;
    }
});


// ---------- Login ----------
loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.textContent = "";
    loginSubmit.disabled = true;

    const payload = {
        username: document.getElementById("login-username").value.trim(),
        password: document.getElementById("login-password").value,
    };

    try {
        const res = await fetch("/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (!res.ok) {
            loginError.textContent = data.detail || "Login failed.";
            loginSubmit.disabled = false;
            return;
        }

        document.getElementById("login-password").value = "";
        await checkAuth();
    } catch (err) {
        console.error(err);
        loginError.textContent = "Network error.";
    } finally {
        loginSubmit.disabled = false;
    }
});


// ---------- Check auth on page load ----------
async function checkAuth() {
    try {
        const res = await fetch("/me");
        if (res.ok) {
            const data = await res.json();
            currentUser = data.user;
            showScreen("chat");
        } else {
            currentUser = null;
            showScreen("login");
        }
    } catch (err) {
        console.error(err);
        showScreen("login");
    }
}


// ---------- Logout ----------
logoutBtn.addEventListener("click", async () => {
    await fetch("/logout", { method: "POST" });
    currentUser = null;
    messageInput.value = "";
    messagesBox.innerHTML = "";
    showScreen("login");
});


// ---------- Messages ----------
async function loadMessages() {
    const res = await fetch("/messages");
    const data = await res.json();
    renderMessages(data.messages);
}

function renderMessages(messages) {
    if (messages.length === 0) {
        messagesBox.innerHTML = '<p class="empty">No messages yet. Be the first to say something.</p>';
        return;
    }
    messagesBox.innerHTML = messages.map(m => {
        const mine = currentUser && m.user_id === currentUser.id;
        const author = m.username ? `@${m.username}` : "unknown";
        return `
            <div class="message-row ${mine ? "mine" : ""}">
                <div class="message-author">${mine ? "you" : escapeHtml(author)}</div>
                <div class="bubble">${escapeHtml(m.text)}</div>
            </div>
        `;
    }).join("");
    messagesBox.scrollTop = messagesBox.scrollHeight;
}

async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;
    messageInput.value = "";
    sendBtn.disabled = true;
    try {
        const res = await fetch("/messages", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
        if (res.status === 401) {
            currentUser = null;
            showScreen("login");
            return;
        }
        await loadMessages();
    } catch (err) {
        console.error(err);
    } finally {
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

sendBtn.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });


// ---------- Helpers ----------
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}


// ---------- Start ----------
checkAuth();