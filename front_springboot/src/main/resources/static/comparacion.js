// Comparacion de politicas de compra sobre la misma demanda simulada.
// Consume /api/inventario/experimento (Spring -> FastAPI, resultado precalculado).
//
// Antes era un solo grafico con stock y ventas de cada politica en dos ejes:
// 8 lineas que no se podian leer. Ahora: tarjetas con la metrica que decide,
// una serie por vez en un solo eje, el balance servicio/stock y la tabla.

// El color sigue al MODELO, no a su posicion: si una corrida trae menos
// modelos, los que quedan no cambian de color. Paleta validada (CVD) con
// scripts/validate_palette.js; la reactiva es la linea base y va en gris.
const COLOR_MODELO = {
  bosque: "#2a78d6",
  logistica: "#eb6834",
  xgb: "#1baf7a",
  mlp: "#eda100",
};
const COLOR_BASE = "#94a3b8";
const COLOR_OTRO = "#6250d6";

const NOTAS = {
  serieAgotados: "Productos sin stock cada día (media de 7 días). Más bajo es mejor.",
  serieVendido: "Unidades vendidas por día (media de 7 días). Más alto es mejor.",
  serieStock: "Unidades en stock sumando todos los productos (media de 7 días).",
};

let datos = null;
let graficoEvolucion = null;
let graficoBalance = null;

const esc = (v) =>
  String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const nf = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });
const pct = (x) => nf.format(x * 100) + "%";

// "predictiva@bosque@0.8" -> "bosque"; "reactiva" -> null
const modeloDe = (p) => (p.politica.includes("@") ? p.politica.split("@")[1] : null);
const colorDe = (p) => {
  const m = modeloDe(p);
  return m === null ? COLOR_BASE : COLOR_MODELO[m] || COLOR_OTRO;
};
// "Con bosque aleatorio (80%)" -> "Bosque aleatorio": el umbral es el mismo para todos
const nombreCorto = (p) => {
  const n = p.etiqueta.replace(/^Con /, "").replace(/ \(\d+%\)$/, "");
  return n.charAt(0).toUpperCase() + n.slice(1);
};

function mediaMovil(serie, ventana) {
  let suma = 0;
  return serie.map((v, i) => {
    suma += v - (i >= ventana ? serie[i - ventana] : 0);
    return Math.round((suma / Math.min(i + 1, ventana)) * 10) / 10;
  });
}

function swatch(color) {
  return '<span aria-hidden="true" class="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style="background:' + color + '"></span>';
}

function pintarResumen() {
  const base = datos.politicas[0];
  const mejor = Math.max(...datos.politicas.map((p) => p.fillRate));

  document.getElementById("resumenComparacion").innerHTML = datos.politicas
    .map((p, i) => {
      const esMejor = p.fillRate === mejor && i > 0;
      const delta = (p.fillRate - base.fillRate) * 100;
      return (
        '<div class="card p-4' + (esMejor ? " ring-2 ring-brand" : "") + '">' +
          '<div class="flex items-baseline gap-2 text-sm font-medium text-slate-700">' +
            swatch(colorDe(p)) + "<span>" + esc(p.etiqueta) + "</span>" +
          "</div>" +
          '<div class="mt-2 text-3xl font-bold tabular-nums text-slate-900">' + pct(p.fillRate) + "</div>" +
          '<div class="text-xs text-slate-500">de la demanda atendida</div>' +
          '<div class="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-600">' +
            (i === 0
              ? "Línea base"
              : '<span class="tabular-nums">' + (delta >= 0 ? "+" : "") + nf.format(delta) + " pts</span>") +
            (esMejor
              ? '<span class="rounded-md bg-green-50 px-1.5 py-0.5 text-xs font-medium text-green-800 ring-1 ring-inset ring-green-200">' +
                '<i class="fas fa-trophy mr-1" aria-hidden="true"></i>Mejor</span>'
              : "") +
          "</div>" +
        "</div>"
      );
    })
    .join("");
}

function pintarTabla() {
  const pol = datos.politicas;
  const max = (k) => Math.max(...pol.map((p) => p[k]));
  const min = (k) => Math.min(...pol.map((p) => p[k]));
  const mejor = { fillRate: max("fillRate"), unidadesNoServidas: min("unidadesNoServidas"), diasAgotadoUtiles: min("diasAgotadoUtiles") };
  const celda = (texto, negrita) =>
    '<td class="px-4 py-2.5 text-right tabular-nums' + (negrita ? " font-semibold text-slate-900" : " text-slate-700") + '">' + texto + "</td>";

  document.getElementById("tablaComparacion").innerHTML = pol
    .map((p) =>
      '<tr class="border-b border-slate-100 last:border-0">' +
        '<th scope="row" class="px-4 py-2.5 text-left font-medium text-slate-900"><span class="flex items-center gap-2">' +
          swatch(colorDe(p)) + esc(p.etiqueta) + "</span></th>" +
        celda(pct(p.fillRate), p.fillRate === mejor.fillRate) +
        celda(p.unidadesNoServidas.toLocaleString("es-CO"), p.unidadesNoServidas === mejor.unidadesNoServidas) +
        celda(p.diasAgotadoUtiles.toLocaleString("es-CO"), p.diasAgotadoUtiles === mejor.diasAgotadoUtiles) +
        celda(p.pedidos.toLocaleString("es-CO"), false) +
        celda(nf.format(p.stockPromedio), false) +
      "</tr>"
    )
    .join("");
}

const ESTILO_EJES = {
  grid: { color: "#e2e8f0" },
  border: { display: false },
};

function pintarEvolucion(serie) {
  document.getElementById("notaEvolucion").textContent = NOTAS[serie];
  document.querySelectorAll("#selectorSerie button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.serie === serie))
  );

  const datasets = datos.politicas.map((p, i) => ({
    label: p.etiqueta,
    data: mediaMovil(p[serie], 7),
    borderColor: colorDe(p),
    backgroundColor: colorDe(p),
    borderWidth: 2,
    borderDash: i === 0 ? [5, 4] : [],
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.2,
  }));

  if (graficoEvolucion) {
    graficoEvolucion.data.datasets = datasets;
    return graficoEvolucion.update();
  }
  const mes = (f) => new Date(f + "T00:00").toLocaleDateString("es-CO", { month: "short", day: "numeric" });
  graficoEvolucion = new Chart(document.getElementById("graficoEvolucion"), {
    type: "line",
    data: { labels: datos.fechas, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "line", boxWidth: 20, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            title: (items) => mes(items[0].label),
            label: (c) => " " + c.dataset.label + ": " + nf.format(c.parsed.y),
          },
        },
      },
      scales: {
        y: { ...ESTILO_EJES, beginAtZero: true },
        x: { ...ESTILO_EJES, grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0, callback: (v) => mes(datos.fechas[v]) } },
      },
    },
  });
}

// Etiqueta cada punto con su nombre: la identidad no depende solo del color.
// Modelos con resultados parecidos caen casi encima: las etiquetas del mismo
// lado se separan en vertical para que no se pisen.
const SEPARACION_ETIQUETAS = 14;
const etiquetasDirectas = {
  id: "etiquetasDirectas",
  afterDatasetsDraw(chart) {
    const { ctx, chartArea } = chart;
    const etiquetas = chart.data.datasets
      .map((d, i) => ({ texto: d.nombre, punto: chart.getDatasetMeta(i).data[0] }))
      .filter((e) => e.punto)
      .map((e) => ({ ...e, derecha: e.punto.x < chartArea.left + chartArea.width * 0.6, y: e.punto.y }))
      .sort((a, b) => a.y - b.y);
    [true, false].forEach((lado) => {
      let previa = -Infinity;
      etiquetas.filter((e) => e.derecha === lado).forEach((e) => {
        e.y = Math.max(e.y, previa + SEPARACION_ETIQUETAS);
        previa = e.y;
      });
    });

    ctx.save();
    ctx.font = "500 11px Inter, ui-sans-serif, system-ui, sans-serif";
    ctx.fillStyle = "#334155";
    ctx.textBaseline = "middle";
    etiquetas.forEach((e) => {
      ctx.textAlign = e.derecha ? "left" : "right";
      ctx.fillText(e.texto, e.punto.x + (e.derecha ? 11 : -11), e.y);
    });
    ctx.restore();
  },
};

function pintarBalance() {
  const datasets = datos.politicas.map((p) => ({
    label: p.etiqueta,
    nombre: nombreCorto(p),
    data: [{ x: p.stockPromedio, y: p.fillRate * 100 }],
    backgroundColor: colorDe(p),
    borderColor: "#ffffff",
    borderWidth: 2,
    pointRadius: 7,
    pointHoverRadius: 9,
  }));

  if (graficoBalance) graficoBalance.destroy();
  graficoBalance = new Chart(document.getElementById("graficoBalance"), {
    type: "scatter",
    data: { datasets },
    plugins: [etiquetasDirectas],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }, // las tarjetas y las etiquetas directas cumplen esa funcion
        tooltip: {
          callbacks: {
            label: (c) => " " + c.dataset.label + ": " + nf.format(c.parsed.y) + "% atendida · stock " + nf.format(c.parsed.x),
          },
        },
      },
      scales: {
        x: { ...ESTILO_EJES, grace: "15%", title: { display: true, text: "Stock promedio por producto" } },
        y: { ...ESTILO_EJES, grace: "10%", title: { display: true, text: "% de la demanda atendida" } },
      },
    },
  });
}

document.getElementById("selectorSerie").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-serie]");
  if (b && datos) pintarEvolucion(b.dataset.serie);
});

async function cargarComparacion() {
  const aviso = document.getElementById("avisoComparacion");
  try {
    const res = await fetch("/api/inventario/experimento");
    if (res.status === 503) {
      aviso.textContent =
        "La comparación aún no se ha generado. Ejecútala desde Modelos o con: python -m inventory_ml.simulation.experimento";
      aviso.classList.remove("hidden");
      return;
    }
    if (!res.ok) throw new Error("HTTP " + res.status);

    datos = await res.json();
    Chart.defaults.font.family = "Inter, ui-sans-serif, system-ui, sans-serif";
    Chart.defaults.color = "#475569";
    pintarResumen();
    pintarEvolucion("serieAgotados");
    pintarBalance();
    pintarTabla();

    document.getElementById("pieComparacion").textContent =
      datos.productos + " productos · " + datos.dias + " días · lead time " +
      datos.leadTimeDias + " días · modelo " + datos.versionModelo +
      " · " + datos.origenModelo + ", no validado con datos reales";
  } catch (err) {
    console.error("Error en cargarComparacion:", err);
    aviso.textContent = "No se pudo cargar la comparación (" + err.message + "). Recarga la página para intentarlo de nuevo.";
    aviso.classList.remove("hidden");
  }
}

cargarComparacion();
