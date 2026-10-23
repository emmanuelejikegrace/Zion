const input = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const messagesBox = document.getElementById("messages");

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
    messagesBox.innerHTML = messages
        .map(m => `<div class="bubble">${escapeHtml(m.text)}</div>`)
        .join("");
    messagesBox.scrollTop = messagesBox.scrollHeight;
}

async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    sendBtn.disabled = true;

    try {
        await fetch("/messages", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        });
        await loadMessages();
    } catch (err) {
        console.error("Failed to send:", err);
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

sendBtn.addEventListener("click", sendMessage);

input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
});

loadMessages();
setInterval(loadMessages, 2000);