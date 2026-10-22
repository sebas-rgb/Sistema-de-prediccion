// Tareas del pipeline (Spring -> FastAPI /api/v1/pipeline).
// Cada formulario con data-tarea="<tipo>" lanza esa tarea con sus campos como
// parametros. La pagina define window.pintarEstado(estado) para su parte propia;
// el panel de la tarea en curso (#tarea) lo pinta este archivo.

const NOMBRE_TAREA = {
  simular_anio: "Regenerar simulación",
  agregar_dias: "Agregar días",
  entrenar: "Entrenar modelo",
  experimento: "Recalcular comparación",
};

let sondeo = null;

async function cargarEstado() {
  try {
    const res = await fetch("/api/pipeline");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const estado = await res.json();
    pintarTarea(estado.tarea);
    window.pintarEstado?.(estado);

    const enCurso = estado.tarea?.estado === "EN_CURSO";
    document.querySelectorAll("form[data-tarea] button").forEach((b) => (b.disabled = enCurso));
    clearTimeout(sondeo);
    if (enCurso) sondeo = setTimeout(cargarEstado, 1500);
  } catch (err) {
    console.error("Error en cargarEstado:", err);
    document.getElementById("tarea").innerHTML =
      '<p class="alert-error" role="alert">No se pudo contactar el servicio de Python. ' +
      "Revisa que FastAPI esté corriendo y recarga la página.</p>";
  }
}

function pintarTarea(t) {
  const cont = document.getElementById("tarea");
  if (!t) {
    cont.innerHTML = '<p class="text-sm text-slate-500">Todavía no se ha ejecutado ninguna tarea.</p>';
    return;
  }
  const estilo = {
    EN_CURSO: ["bg-brand-50 text-brand-ink ring-brand-100", "fa-circle-notch fa-spin", "En curso"],
    OK: ["bg-green-50 text-green-800 ring-green-200", "fa-check", "Terminó bien"],
    ERROR: ["bg-red-50 text-red-800 ring-red-200", "fa-triangle-exclamation", "Falló"],
  }[t.estado];
  const hora = (iso) => (iso ? new Date(iso).toLocaleTimeString("es-CO") : "");

  cont.innerHTML =
    '<div class="mb-3 flex flex-wrap items-center gap-2 text-sm">' +
      '<span class="font-semibold text-slate-900"></span>' +
      '<span class="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-medium ring-1 ring-inset ' + estilo[0] + '">' +
        '<i class="fas ' + estilo[1] + '" aria-hidden="true"></i>' + estilo[2] + "</span>" +
      '<span class="text-slate-500">' + hora(t.inicio) + (t.fin ? " – " + hora(t.fin) : "") + "</span>" +
    "</div>" +
    '<pre class="max-h-72 overflow-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed text-slate-100"></pre>';
  cont.querySelector("span").textContent = NOMBRE_TAREA[t.tipo] || t.tipo;
  const pre = cont.querySelector("pre");
  pre.textContent = t.log.join("\n") || "Iniciando…";
  pre.scrollTop = pre.scrollHeight;
  if (t.estado === "ERROR") {
    cont.insertAdjacentHTML("beforeend",
      '<p class="mt-2 text-sm text-red-700">Revisa la última línea del registro: ahí está la causa.</p>');
  }
}

document.querySelectorAll("form[data-tarea]").forEach((form) => {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (form.dataset.confirmar && !confirm(form.dataset.confirmar)) return;

    const cuerpo = { tipo: form.dataset.tarea };
    new FormData(form).forEach((v, k) => (cuerpo[k] = isNaN(v) || v === "" ? v : Number(v)));
    // el boton pulsado puede fijar un parametro (ej. algoritmo, dias rapidos)
    const boton = e.submitter;
    if (boton?.name) cuerpo[boton.name] = isNaN(boton.value) ? boton.value : Number(boton.value);

    const res = await fetch("/api/pipeline/tareas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    if (res.status === 409) {
      document.getElementById("tarea").insertAdjacentHTML("afterbegin",
        '<p class="alert-error mb-3" role="alert">Ya hay una tarea en curso. Espera a que termine.</p>');
    } else if (!res.ok) {
      document.getElementById("tarea").insertAdjacentHTML("afterbegin",
        '<p class="alert-error mb-3" role="alert">No se pudo lanzar la tarea (error ' + res.status +
        "). Revisa los valores e inténtalo de nuevo.</p>");
    }
    cargarEstado();
  });
});

cargarEstado();
