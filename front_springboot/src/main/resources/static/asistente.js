// Chat con el asistente de inventario.
// El navegador nunca ve la API key: va a /api/inventario/asistente (Spring),
// que reenvía a FastAPI, que es quien tiene la clave.

// Las dos ultimas obligan al agente a usar herramientas: no se pueden
// responder con el resumen inyectado.
const SUGERENCIAS = [
  "¿Qué productos debo priorizar esta semana?",
  "¿Cuánto stock necesita el 611270 para dejar de ser riesgo alto?",
  "¿Hay evidencia de que el modelo mejore el servicio? Dame cifras.",
];

function burbuja(texto, esUsuario) {
  const div = document.createElement("div");
  div.className = esUsuario ? "flex justify-end" : "flex justify-start";
  div.innerHTML =
    '<div class="max-w-[85%] px-4 py-2 rounded-2xl text-sm whitespace-pre-wrap ' +
    (esUsuario
      ? "bg-sky-600 text-white rounded-br-sm"
      : "bg-gray-100 text-gray-800 rounded-bl-sm") +
    '">' +
    texto.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") +
    "</div>";
  return div;
}

function pensando() {
  const div = document.createElement("div");
  div.className = "flex justify-start";
  div.id = "burbujaPensando";
  div.innerHTML =
    '<div class="px-4 py-2 rounded-2xl bg-gray-100 text-gray-500 text-sm">' +
    '<i class="fas fa-circle-notch fa-spin mr-2"></i>Analizando el inventario…</div>';
  return div;
}

async function enviarPregunta(texto) {
  const hilo = document.getElementById("hiloChat");
  const input = document.getElementById("inputChat");
  const boton = document.getElementById("btnEnviarChat");

  hilo.appendChild(burbuja(texto, true));
  hilo.appendChild(pensando());
  hilo.scrollTop = hilo.scrollHeight;
  input.value = "";
  input.disabled = true;
  boton.disabled = true;

  try {
    const res = await fetch("/api/inventario/asistente", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta: texto, fecha: fechaActual || null }),
    });

    document.getElementById("burbujaPensando")?.remove();

    if (res.status === 503) {
      hilo.appendChild(
        burbuja(
          "El asistente no está disponible. Verifica que FastAPI esté corriendo y que la variable LLM_API_KEY esté configurada.",
          false
        )
      );
    } else if (!res.ok) {
      hilo.appendChild(burbuja("Error " + res.status + " al consultar el asistente.", false));
    } else {
      const data = await res.json();
      hilo.appendChild(burbuja(data.respuesta, false));

      const pie = document.createElement("div");
      pie.className = "text-xs text-gray-400 px-2";
      pie.textContent =
        "Contexto: inventario del " + data.fechaContexto +
        " · modelo predictivo " + data.versionModeloPrediccion +
        " (" + data.origenModelo + ", no validado)" +
        (data.tokensEntrada ? " · " + (data.tokensEntrada + data.tokensSalida) + " tokens" : "");
      hilo.appendChild(pie);

      // Evidencia visible de que es un agente: que consulto por su cuenta.
      if (data.herramientasUsadas && data.herramientasUsadas.length) {
        const usadas = document.createElement("div");
        usadas.className = "flex flex-wrap gap-1 px-2 mt-1";
        usadas.innerHTML = data.herramientasUsadas
          .map(
            (h) =>
              '<span class="px-2 py-0.5 text-[10px] rounded-full bg-violet-50 ' +
              'text-violet-700 border border-violet-200">' +
              '<i class="fas fa-wrench mr-1"></i>' + h + "</span>"
          )
          .join("");
        hilo.appendChild(usadas);
      }
    }
  } catch (err) {
    document.getElementById("burbujaPensando")?.remove();
    console.error("Error en el asistente:", err);
    hilo.appendChild(burbuja("No se pudo contactar el servicio: " + err.message, false));
  } finally {
    input.disabled = false;
    boton.disabled = false;
    input.focus();
    hilo.scrollTop = hilo.scrollHeight;
  }
}

function iniciarChat() {
  const sugerencias = document.getElementById("sugerenciasChat");
  sugerencias.innerHTML = SUGERENCIAS.map(
    (s) =>
      '<button class="px-3 py-1 text-xs rounded-full bg-sky-50 text-sky-700 ' +
      'hover:bg-sky-100 border border-sky-200 transition">' + s + "</button>"
  ).join("");
  sugerencias.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => enviarPregunta(b.textContent))
  );

  const input = document.getElementById("inputChat");
  const boton = document.getElementById("btnEnviarChat");

  const enviar = () => {
    const texto = input.value.trim();
    if (texto.length >= 3) enviarPregunta(texto);
  };

  boton.addEventListener("click", enviar);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  });
}

iniciarChat();
