// Reemplaza el bloque <script defer> que hacia fetch('/temp/validacion_externa.csv').
// Ahora consume /api/inventario, que Spring proxea hacia FastAPI.
//
// Cambios respecto al anterior:
//   - la paginacion la hace el servidor (antes se cargaba el CSV entero en memoria)
//   - se elimino la columna "Agotado 30d": es la etiqueta real y solo se conoce
//     30 dias despues. En una vista del dia actual seria mostrar el futuro.
//   - se muestra el estado del modelo (SIMULADO / NO VALIDADO)

const TAM_PAGINA = 10;
let paginaActual = 1;
let fechaActual = null;
let busqueda = "";
let sedeActual = ""; // "" = vista general (simulacion); con sede, ultimo inventario real

const RIESGO_ESTILO = {
  ALTO:  "bg-red-50 text-red-800 ring-red-200",
  MEDIO: "bg-amber-50 text-amber-900 ring-amber-200",
  BAJO:  "bg-green-50 text-green-800 ring-green-200",
};

// Todo lo que viene de la API pasa por aqui antes de entrar a innerHTML
const esc = (v) =>
    String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const nf = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });

function filaMensaje(texto, clase) {
  const body = document.getElementById("tableBody");
  body.innerHTML = '<tr><td colspan="6" class="py-8 text-center ' + clase + '">' + esc(texto) + "</td></tr>";
  body.setAttribute("aria-busy", "false");
}

async function cargarInventario() {
  const params = new URLSearchParams({ pagina: paginaActual, tamanoPagina: TAM_PAGINA });
  if (fechaActual) params.set("fecha", fechaActual);
  if (busqueda) params.set("codigo", busqueda);
  if (sedeActual) params.set("sede", sedeActual);

  document.getElementById("tableBody").setAttribute("aria-busy", "true");
  try {
    const res = await fetch("/api/inventario?" + params);
    if (res.status === 503) return mostrarError("Servicio de prediccion no disponible");
    if (!res.ok) return mostrarError("Error " + res.status);
    renderizar(await res.json());
  } catch (err) {
    // Distinguir un fallo de red de un error al pintar: antes ambos decian
    // "no se pudo contactar" y eso mandaba a depurar al sitio equivocado.
    console.error("Error en cargarInventario:", err);
    mostrarError(
        err instanceof TypeError && String(err).includes("fetch")
            ? "No se pudo contactar el servicio"
            : "Error al procesar la respuesta: " + err.message
    );
  }
}

function mostrarError(msg) {
  filaMensaje(msg + ". Recarga la página o inténtalo en unos minutos.", "text-red-700");
  document.getElementById("paginationContainer").innerHTML = "";
}

function renderizar(data) {
  // La fecha de una sede es la del ultimo Excel real, no la de la simulacion:
  // no debe pisar la fecha elegida para la vista general.
  if (!sedeActual) {
    fechaActual = data.fecha;
    window.fechaInventario = data.fecha; // el asistente pregunta sobre esta fecha
  }
  const body = document.getElementById("tableBody");

  if (!data.items.length) {
    filaMensaje(busqueda ? "Ningún código coincide con «" + busqueda + "»." : "No hay productos para esta fecha.", "text-slate-500");
  } else {
    body.innerHTML = data.items
        .map(function (row) {
          const pct = (row.probabilidadAgotamiento * 100).toFixed(1);
          const estilo = RIESGO_ESTILO[row.nivelRiesgo] || "bg-gray-100 text-gray-700";
          const sinStock = row.stockActual <= 0;
          return (
              '<tr class="border-b border-slate-100 last:border-0 hover:bg-slate-50">' +
              '<td class="px-4 py-2.5 font-medium tabular-nums">' + esc(row.codigo) + "</td>" +
              '<td class="px-4 py-2.5 text-slate-600 tabular-nums">' + esc(row.fecha) + "</td>" +
              '<td class="px-4 py-2.5 text-right tabular-nums ' + (sinStock ? "font-semibold text-red-700" : "") + '">' +
              nf.format(row.stockActual) + (sinStock ? " · agotado" : "") + "</td>" +
              '<td class="px-4 py-2.5">' + esc(row.clase) + "</td>" +
              '<td class="px-4 py-2.5 text-right tabular-nums">' + nf.format(row.consumoPromedio) + "</td>" +
              '<td class="px-4 py-2.5"><span class="' + estilo + ' inline-block whitespace-nowrap rounded-md px-2 py-0.5 font-medium ring-1 ring-inset tabular-nums">' +
              esc(row.nivelRiesgo) + " · " + pct + "%</span></td>" +
              "</tr>"
          );
        })
        .join("");
    body.setAttribute("aria-busy", "false");
  }

  renderizarPaginacion(data);

  const experimental = data.estadoValidacion && data.estadoValidacion !== "VALIDADO";
  document.getElementById("statsInfo").innerHTML =
      (sedeActual
          ? "Sede <strong>" + esc(sedeActual) + "</strong> · inventario real del <strong>"
          : "Inventario del <strong>") + esc(data.fecha) + "</strong> · " +
      "<strong>" + nf.format(data.total) + "</strong> productos · modelo " + esc(data.versionModelo) +
      (experimental
          ? ' <span class="ml-1 inline-block rounded-md bg-amber-50 px-2 py-0.5 text-amber-900 ring-1 ring-inset ring-amber-200">' +
          '<i class="fas fa-triangle-exclamation mr-1" aria-hidden="true"></i>Modelo ' +
          esc(data.origenModelo) + ", no validado con datos reales</span>"
          : "");
}

function renderizarPaginacion(data) {
  const total = Math.ceil(data.total / data.tamanoPagina);
  const cont = document.getElementById("paginationContainer");
  if (total <= 1) return (cont.innerHTML = "");

  let html = "";
  const btn = (p, txt, activo) =>
      '<button type="button" data-pagina="' + p + '"' +
      (activo ? ' aria-current="page"' : "") +
      (typeof txt === "number" ? ' aria-label="Página ' + p + '"' : "") +
      ' class="btn min-w-[2.5rem] px-3 py-1.5 text-sm ' +
      (activo ? "bg-brand text-white" : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50") + '">' +
      txt + "</button>";

  if (data.pagina > 1) html += btn(data.pagina - 1, "Anterior", false);
  for (let i = Math.max(1, data.pagina - 2); i <= Math.min(total, data.pagina + 2); i++) {
    html += btn(i, i, i === data.pagina);
  }
  if (data.pagina < total) html += btn(data.pagina + 1, "Siguiente", false);
  cont.innerHTML = html;
}

document.getElementById("paginationContainer").addEventListener("click", function (e) {
  const b = e.target.closest("button[data-pagina]");
  if (!b) return;
  paginaActual = Number(b.dataset.pagina);
  cargarInventario();
  document.getElementById("tituloInventario").closest("section").scrollIntoView({ block: "start" });
});

// Busqueda: la filtra el servidor, con debounce para no disparar una peticion por tecla
let debounce;
document.getElementById("searchInventory").addEventListener("input", function (e) {
  clearTimeout(debounce);
  debounce = setTimeout(function () {
    busqueda = e.target.value.trim();
    paginaActual = 1;
    cargarInventario();
  }, 300);
});

// Descargar CSV: exporta el snapshot completo de la fecha actual (con el filtro
// aplicado), recorriendo las paginas de la API. Tope de seguridad para no
// intentar bajar un catalogo entero al navegador.
const MAX_PAGINAS_EXPORT = 10;
const TAM_EXPORT = 200;

document.getElementById("downloadCSV").addEventListener("click", async function () {
  const boton = this;
  const textoOriginal = boton.innerHTML;
  boton.disabled = true;
  boton.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Generando…';

  try {
    const filas = [];
    let pagina = 1;
    let total = Infinity;

    while (filas.length < total && pagina <= MAX_PAGINAS_EXPORT) {
      const params = new URLSearchParams({ pagina: pagina, tamanoPagina: TAM_EXPORT });
      if (fechaActual) params.set("fecha", fechaActual);
      if (busqueda) params.set("codigo", busqueda);
      if (sedeActual) params.set("sede", sedeActual);

      const res = await fetch("/api/inventario?" + params);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      total = data.total;
      filas.push.apply(filas, data.items);
      if (!data.items.length) break;
      pagina++;
    }

    const cabecera = [
      "codigo", "fecha", "stock_actual", "clase", "consumo_promedio",
      "probabilidad_agotamiento", "nivel_riesgo",
    ];
    const csv = [cabecera.join(",")]
        .concat(
            filas.map(function (r) {
              return [
                r.codigo, r.fecha, r.stockActual, r.clase, r.consumoPromedio,
                r.probabilidadAgotamiento, r.nivelRiesgo,
              ]
                  .map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; })
                  .join(",");
            })
        )
        .join("\n");

    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "inventario_" + (sedeActual ? sedeActual + "_" : "") + (fechaActual || "actual") + ".csv";
    a.click();
    URL.revokeObjectURL(url);

    if (filas.length < total) {
      avisoExport("Se exportaron " + filas.length + " de " + total +
          " productos (máximo por descarga). Filtra por código para bajar el resto.", false);
    }
  } catch (err) {
    console.error(err);
    avisoExport("No se pudo generar el CSV. Inténtalo de nuevo en unos minutos.", true);
  } finally {
    boton.disabled = false;
    boton.innerHTML = textoOriginal;
  }
});

function avisoExport(texto, esError) {
  const p = document.createElement("p");
  p.setAttribute("role", esError ? "alert" : "status");
  p.className = "mt-1 text-sm " + (esError ? "text-red-700" : "text-amber-900");
  p.textContent = texto;
  document.getElementById("statsInfo").after(p);
  setTimeout(() => p.remove(), 8000);
}

// Selector de fecha: la simulacion cubre un ano completo
fetch("/api/inventario/fechas")
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (rango) {
      if (!rango) return;
      const input = document.getElementById("fechaInventario");
      if (!input) return;
      input.min = rango.primeraFecha;
      input.max = rango.ultimaFecha;
      input.value = rango.ultimaFecha;
      input.addEventListener("change", function (e) {
        fechaActual = e.target.value;
        paginaActual = 1;
        cargarInventario();
      });
    });

// Sedes: cada una se puntua con su propio stock y consumo. Si Python aun no
// genero los perfiles (ingestion/sedes.py), el selector se queda en "General".
fetch("/api/inventario/sedes")
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (!data) return;
      const select = document.getElementById("sedeInventario");
      data.sedes.forEach(function (s) { select.add(new Option(s, s)); });
      select.addEventListener("change", function (e) {
        sedeActual = e.target.value;
        // Por sede solo existe el ultimo snapshot real: la fecha no aplica
        document.getElementById("fechaInventario").disabled = Boolean(sedeActual);
        paginaActual = 1;
        cargarInventario();
      });
    });

cargarInventario();