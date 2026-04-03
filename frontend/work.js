async function sendMessage() {
    const input = document.getElementById("userInput");
    const message = input.value;

    if (!message) return;

    // Show user message in chat box
    const chatBox = document.getElementById("chatBox");
    chatBox.innerHTML += `<div><b>You:</b> ${message}</div>`;

    const response = await fetch("http://127.0.0.1:8000/ask", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ message })
    });

    const data = await response.json();

    // Show AI response
    chatBox.innerHTML += `<div><b>LexChat:</b> ${data.reply}</div>`;
    chatBox.scrollTop = chatBox.scrollHeight; // scroll to bottom

    input.value = "";
}