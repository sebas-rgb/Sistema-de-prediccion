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

// El modelo responde en markdown (negritas, listas, tablas). Lo del usuario
// va como texto plano; lo del modelo se pasa por marked + DOMPurify.
function burbuja(texto, esUsuario) {
  const div = document.createElement("div");
  div.className = esUsuario ? "flex justify-end" : "flex justify-start";

  const cuerpo = document.createElement("div");
  cuerpo.className =
    "max-w-[85%] px-4 py-2 rounded-2xl text-sm " +
    (esUsuario
      ? "bg-brand text-white rounded-br-sm whitespace-pre-wrap"
      : "bg-slate-100 text-slate-800 rounded-bl-sm md burbuja-md");

  if (esUsuario || !window.marked || !window.DOMPurify) {
    cuerpo.textContent = texto;                    // sin librerias: texto plano
    if (!esUsuario) cuerpo.classList.add("whitespace-pre-wrap");
  } else {
    cuerpo.innerHTML = DOMPurify.sanitize(
      marked.parse(texto, { breaks: true, gfm: true })
    );
  }

  div.appendChild(cuerpo);
  return div;
}

function pensando() {
  const div = document.createElement("div");
  div.className = "flex justify-start";
  div.id = "burbujaPensando";
  div.innerHTML =
    '<div class="px-4 py-2 rounded-2xl bg-slate-100 text-slate-600 text-sm">' +
    '<i class="fas fa-circle-notch fa-spin mr-2" aria-hidden="true"></i>Analizando el inventario…</div>';
  return div;
}

// La pregunta corre en segundo plano en Python: aqui solo se encola y se
// pregunta "¿ya?" cada pocos segundos. El id va a sessionStorage, asi que si
// cambias de pagina a mitad de respuesta, la pagina nueva retoma la espera.
// (Antes era un solo fetch de hasta un minuto: al navegar se cancelaba y el
// chat guardaba "Failed to fetch".)
const CLAVE_PENDIENTE = "asistente.pendiente";
const INTERVALO_MS = 2000;
const ESPERA_MAX_MS = 4 * 60 * 1000;

function bloquear(si) {
  document.getElementById("inputChat").disabled = si;
  document.getElementById("btnEnviarChat").disabled = si;
}

function cerrarEspera(nodos) {
  const hilo = document.getElementById("hiloChat");
  document.getElementById("burbujaPensando")?.remove();
  nodos.forEach((n) => hilo.appendChild(n));
  try { sessionStorage.removeItem(CLAVE_PENDIENTE); } catch (e) {}
  bloquear(false);
  hilo.scrollTop = hilo.scrollHeight;
  guardarHilo();
  document.getElementById("inputChat").focus();
}

// Python devuelve el resultado tal cual (snake_case): Spring solo lo reenvia.
function nodosRespuesta(data) {
  const nodos = [burbuja(data.respuesta, false)];

  const pie = document.createElement("div");
  pie.className = "text-xs text-slate-500 px-2";
  pie.textContent =
    "Contexto: inventario del " + data.fecha_contexto +
    " · modelo predictivo " + data.version_modelo_prediccion +
    " (" + data.origen_modelo + ", no validado) · " + data.modelo_llm +
    (data.tokens_entrada ? " · " + (data.tokens_entrada + data.tokens_salida) + " tokens" : "");
  nodos.push(pie);

  // Evidencia visible de que es un agente: que consulto por su cuenta.
  if (data.herramientas_usadas && data.herramientas_usadas.length) {
    const usadas = document.createElement("div");
    usadas.className = "flex flex-wrap gap-1 px-2 mt-1";
    data.herramientas_usadas.forEach((h) => {
      const chip = document.createElement("span");
      chip.className = "px-2 py-0.5 text-xs rounded-md bg-slate-100 text-slate-700";
      chip.innerHTML = '<i class="fas fa-wrench mr-1" aria-hidden="true"></i>';
      chip.append(h);
      usadas.appendChild(chip);
    });
    nodos.push(usadas);
  }
  return nodos;
}

async function esperarRespuesta(id, desde) {
  while (Date.now() - desde < ESPERA_MAX_MS) {
    await new Promise((r) => setTimeout(r, INTERVALO_MS));
    let res;
    try {
      res = await fetch("/api/inventario/asistente/tareas/" + id);
    } catch (err) {
      continue; // un fallo de red puntual no es el final: se reintenta
    }
    if (res.status === 404) {
      return cerrarEspera([burbuja("Se perdió la pregunta porque el servidor se reinició. Vuelve a enviarla.", false)]);
    }
    if (!res.ok) continue;
    const t = await res.json();
    if (t.estado === "OK") return cerrarEspera(nodosRespuesta(t.resultado));
    if (t.estado === "ERROR") {
      return cerrarEspera([burbuja("El asistente no pudo responder: " + t.detalle + " Vuelve a intentarlo en un momento.", false)]);
    }
  }
  cerrarEspera([burbuja("El asistente tardó demasiado en responder. Vuelve a enviar la pregunta.", false)]);
}

async function enviarPregunta(texto) {
  const hilo = document.getElementById("hiloChat");
  hilo.appendChild(burbuja(texto, true));
  hilo.appendChild(pensando());
  hilo.scrollTop = hilo.scrollHeight;
  document.getElementById("inputChat").value = "";
  bloquear(true);
  guardarHilo();

  try {
    const res = await fetch("/api/inventario/asistente/tareas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // la fecha la publica la pagina de Inventario; en las demas se usa la ultima
      body: JSON.stringify({ pregunta: texto, fecha: window.fechaInventario || null }),
    });
    if (!res.ok) {
      return cerrarEspera([burbuja(
        res.status === 503
          ? "El asistente no está disponible ahora. Si sigue así, revisa que FastAPI esté corriendo."
          : "El asistente respondió con un error (" + res.status + "). Vuelve a enviar la pregunta.",
        false
      )]);
    }
    const { id } = await res.json();
    const desde = Date.now();
    try { sessionStorage.setItem(CLAVE_PENDIENTE, JSON.stringify({ id, desde })); } catch (e) {}
    esperarRespuesta(id, desde);
  } catch (err) {
    console.error("Error en el asistente:", err);
    cerrarEspera([burbuja("No se pudo contactar el asistente. Revisa tu conexión y vuelve a intentarlo.", false)]);
  }
}

// La conversacion sobrevive al cambio de pagina durante la sesion. Solo se
// guarda HTML que ya genero este archivo (texto plano o markdown saneado).
const CLAVE_HILO = "asistente.hilo";
const CLAVE_ABIERTO = "asistente.abierto";

function guardarHilo() {
  try { sessionStorage.setItem(CLAVE_HILO, document.getElementById("hiloChat").innerHTML); } catch (e) {}
}

function abrirPanel(abrir, enfocar = true) {
  const panel = document.getElementById("panelAsistente");
  const disparador = document.getElementById("abrirAsistente");
  panel.toggleAttribute("data-abierto", abrir);
  document.body.classList.toggle("con-asistente", abrir);
  panel.inert = !abrir;
  disparador.setAttribute("aria-expanded", String(abrir));
  disparador.hidden = abrir;
  try { localStorage.setItem(CLAVE_ABIERTO, abrir ? "1" : ""); } catch (e) {}
  if (!enfocar) return;
  (abrir ? document.getElementById("inputChat") : disparador).focus();
}

function iniciarChat() {
  const hilo = document.getElementById("hiloChat");
  try { hilo.innerHTML = sessionStorage.getItem(CLAVE_HILO) || ""; } catch (e) {}
  document.getElementById("burbujaPensando")?.remove();
  // Si se cambio de pagina a mitad de respuesta, se retoma la espera
  let pendiente = null;
  try { pendiente = JSON.parse(sessionStorage.getItem(CLAVE_PENDIENTE) || "null"); } catch (e) {}
  if (pendiente) {
    hilo.appendChild(pensando());
    bloquear(true);
    esperarRespuesta(pendiente.id, pendiente.desde);
  }

  document.getElementById("abrirAsistente").addEventListener("click", () => abrirPanel(true));
  document.getElementById("cerrarAsistente").addEventListener("click", () => abrirPanel(false));
  document.getElementById("limpiarAsistente").addEventListener("click", () => {
    hilo.replaceChildren();
    guardarHilo();
    document.getElementById("inputChat").focus();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.getElementById("panelAsistente").hasAttribute("data-abierto")) abrirPanel(false);
  });

  let abierto = false;
  try { abierto = localStorage.getItem(CLAVE_ABIERTO) === "1"; } catch (e) {}
  if (abierto) {
    // sin animacion al reabrir en otra pagina: solo se anima lo que hace el usuario
    const panel = document.getElementById("panelAsistente");
    panel.style.transition = document.body.style.transition = "none";
    abrirPanel(true, false);
    panel.offsetWidth;
    panel.style.transition = document.body.style.transition = "";
  }
  hilo.scrollTop = hilo.scrollHeight;

  const sugerencias = document.getElementById("sugerenciasChat");
  sugerencias.innerHTML = SUGERENCIAS.map(
    (s) =>
      '<button type="button" class="btn px-3 py-1.5 text-sm font-medium rounded-full ' +
      'border border-brand-100 bg-brand-50 text-brand-ink hover:bg-brand-100">' + s + "</button>"
  ).join("");
  sugerencias.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => enviarPregunta(b.textContent))
  );

  // El form valida minlength/required de forma nativa
  document.getElementById("formChat").addEventListener("submit", (e) => {
    e.preventDefault();
    const texto = document.getElementById("inputChat").value.trim();
    if (texto) enviarPregunta(texto);
  });
}

iniciarChat();
