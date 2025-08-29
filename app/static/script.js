async function sendMessage() {
    let input = document.getElementById("userInput");
    let message = input.value;
    if (!message) return;

    // Mostrar mensaje del usuario
    document.getElementById("messages").innerHTML += `<p><b>Tú:</b> ${message}</p>`;
    input.value = "";

    // Enviar al backend
    let res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: message })
    });

    let data = await res.json();
    document.getElementById("messages").innerHTML += `<p><b>Bot:</b> ${data.response}</p>`;
}
