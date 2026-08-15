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

const RIESGO_ESTILO = {
  ALTO:  "bg-red-100 text-red-700",
  MEDIO: "bg-yellow-100 text-yellow-700",
  BAJO:  "bg-green-100 text-green-700",
};

async function cargarInventario() {
  const params = new URLSearchParams({ pagina: paginaActual, tamanoPagina: TAM_PAGINA });
  if (fechaActual) params.set("fecha", fechaActual);
  if (busqueda) params.set("codigo", busqueda);

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
  document.getElementById("tableBody").innerHTML =
      '<tr class="text-center text-red-500"><td colspan="6" class="py-8">' + msg + "</td></tr>";
  document.getElementById("paginationContainer").innerHTML = "";
}

function renderizar(data) {
  fechaActual = data.fecha;
  const body = document.getElementById("tableBody");

  if (!data.items.length) {
    body.innerHTML =
        '<tr class="text-center text-gray-500"><td colspan="6" class="py-8">No hay resultados</td></tr>';
  } else {
    body.innerHTML = data.items
        .map(function (row) {
          const pct = (row.probabilidadAgotamiento * 100).toFixed(1);
          const estilo = RIESGO_ESTILO[row.nivelRiesgo] || "bg-gray-100 text-gray-700";
          const stockColor = row.stockActual <= 0 ? "text-red-600" : "text-green-600";
          return (
              '<tr class="border-b hover:bg-sky-50 transition-colors">' +
              '<td class="px-4 py-2 font-mono text-sky-600">' + row.codigo + "</td>" +
              '<td class="px-4 py-2 text-gray-600">' + row.fecha + "</td>" +
              '<td class="px-4 py-2 text-center font-semibold ' + stockColor + '">' + row.stockActual + "</td>" +
              '<td class="px-4 py-2 text-center"><span class="bg-sky-100 text-sky-700 px-2 py-1 rounded">' + row.clase + "</span></td>" +
              '<td class="px-4 py-2 text-center">' + row.consumoPromedio.toFixed(2) + "</td>" +
              '<td class="px-4 py-2 text-center"><span class="' + estilo + ' px-2 py-1 rounded font-semibold">' +
              pct + "% · " + row.nivelRiesgo + "</span></td>" +
              "</tr>"
          );
        })
        .join("");
  }

  renderizarPaginacion(data);

  const experimental = data.estadoValidacion && data.estadoValidacion !== "VALIDADO";
  document.getElementById("statsInfo").innerHTML =
      "Snapshot del <strong>" + data.fecha + "</strong> · " +
      "<strong>" + data.total + "</strong> productos · modelo " + data.versionModelo +
      (experimental
          ? ' <span class="bg-amber-100 text-amber-800 px-2 py-0.5 rounded">Modelo ' +
          data.origenModelo + " · no validado con datos reales</span>"
          : "");
}

function renderizarPaginacion(data) {
  const total = Math.ceil(data.total / data.tamanoPagina);
  const cont = document.getElementById("paginationContainer");
  if (total <= 1) return (cont.innerHTML = "");

  let html = "";
  const btn = (p, txt, activo) =>
      '<button onclick="irPagina(' + p + ')" class="px-3 py-2 rounded ' +
      (activo ? "bg-sky-600 text-white" : "bg-gray-200 hover:bg-gray-300") + '">' + txt + "</button>";

  if (data.pagina > 1) html += btn(data.pagina - 1, "Anterior", false);
  for (let i = Math.max(1, data.pagina - 2); i <= Math.min(total, data.pagina + 2); i++) {
    html += btn(i, i, i === data.pagina);
  }
  if (data.pagina < total) html += btn(data.pagina + 1, "Siguiente", false);
  cont.innerHTML = html;
}

window.irPagina = function (p) {
  paginaActual = p;
  cargarInventario();
  window.scrollTo({ top: 0, behavior: "smooth" });
};

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
  boton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Generando...';

  try {
    const filas = [];
    let pagina = 1;
    let total = Infinity;

    while (filas.length < total && pagina <= MAX_PAGINAS_EXPORT) {
      const params = new URLSearchParams({ pagina: pagina, tamanoPagina: TAM_EXPORT });
      if (fechaActual) params.set("fecha", fechaActual);
      if (busqueda) params.set("codigo", busqueda);

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
    a.download = "inventario_" + (fechaActual || "actual") + ".csv";
    a.click();
    URL.revokeObjectURL(url);

    if (filas.length < total) {
      alert("Se exportaron " + filas.length + " de " + total + " registros (limite de seguridad).");
    }
  } catch (err) {
    console.error(err);
    alert("No se pudo generar el CSV.");
  } finally {
    boton.disabled = false;
    boton.innerHTML = textoOriginal;
  }
});

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

cargarInventario();