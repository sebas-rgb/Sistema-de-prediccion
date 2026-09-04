// Gráfico comparativo: reposición reactiva vs. predictiva sobre la misma demanda.
// Consume /api/inventario/experimento (Spring -> FastAPI, resultado precalculado).

// Una entrada por politica, en el orden que las manda el backend: la reactiva
// siempre primera, luego un brazo por modelo. Si se agrega un modelo mas, aqui
// no se toca nada mientras haya color libre.
const COLORES = ["#dc2626", "#059669", "#2563eb", "#d97706", "#7c3aed"];

let graficoComparacion = null;

const color = (i) => COLORES[i % COLORES.length];

function pintarResumen(data) {
  const cont = document.getElementById("resumenComparacion");
  const base = data.politicas[0];

  cont.innerHTML = data.politicas
    .map((p, i) => {
      const c = color(i);
      const menos = base.diasAgotadoUtiles - p.diasAgotadoUtiles;
      const detalle =
        i === 0
          ? p.diasAgotadoUtiles.toLocaleString() + " días-producto sin stock (línea base)"
          : menos.toLocaleString() + " días-producto menos · " +
            (p.pedidos - base.pedidos) + " pedidos extra";

      return (
        '<div class="flex-1 min-w-[180px] p-4 rounded-xl border" style="border-color:' + c + '33">' +
          '<div class="text-xs uppercase tracking-wide text-gray-500">' + p.etiqueta + "</div>" +
          '<div class="text-2xl font-bold" style="color:' + c + '">' +
            (p.fillRate * 100).toFixed(1) + "%</div>" +
          '<div class="text-xs text-gray-500">demanda atendida</div>' +
          '<div class="text-xs text-gray-500 mt-1">' + detalle + "</div>" +
        "</div>"
      );
    })
    .join("");
}

function pintarGrafico(data) {
  const ctx = document.getElementById("graficoComparacion");
  if (graficoComparacion) graficoComparacion.destroy();

  // Stock disponible (eje izquierdo) contra unidades entregadas (eje derecho).
  // Dos ejes porque el stock total ronda las 8.000 unidades y lo vendido en un
  // dia, 300: en un solo eje la linea de ventas quedaria pegada al cero.
  // Sin relleno: con tres politicas las areas superpuestas se vuelven ilegibles.
  const datasets = [];
  data.politicas.forEach((p, i) => {
    datasets.push({
      label: "Stock · " + p.etiqueta,
      data: p.serieStock,
      borderColor: color(i),
      fill: false,
      pointRadius: 0,
      borderWidth: 2.5,
      yAxisID: "y",
    });
    datasets.push({
      label: "Vendido · " + p.etiqueta,
      data: p.serieVendido,
      borderColor: color(i),
      borderDash: [4, 3],
      fill: false,
      pointRadius: 0,
      borderWidth: 1.25,
      yAxisID: "yVendido",
    });
  });

  graficoComparacion = new Chart(ctx, {
    type: "line",
    data: { labels: data.fechas, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top", labels: { boxWidth: 24, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (c) =>
              c.dataset.label + ": " + c.parsed.y.toLocaleString() + " unidades",
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          position: "left",
          title: { display: true, text: "Unidades en stock" },
        },
        yVendido: {
          beginAtZero: true,
          position: "right",
          grid: { drawOnChartArea: false },
          title: { display: true, text: "Unidades vendidas por día" },
        },
        x: {
          ticks: { maxTicksLimit: 12 },
          title: { display: true, text: "Día de la simulación" },
        },
      },
    },
  });
}

async function cargarComparacion() {
  const aviso = document.getElementById("avisoComparacion");
  try {
    const res = await fetch("/api/inventario/experimento");
    if (res.status === 503) {
      aviso.textContent =
        "Comparación no generada. Ejecuta: python -m inventory_ml.simulation.experimento";
      aviso.classList.remove("hidden");
      return;
    }
    if (!res.ok) throw new Error("HTTP " + res.status);

    const data = await res.json();
    pintarResumen(data);
    pintarGrafico(data);

    document.getElementById("pieComparacion").textContent =
      data.productos + " productos · " + data.dias + " días · lead time " +
      data.leadTimeDias + " días · modelo " + data.versionModelo +
      " · " + data.origenModelo + ", no validado con datos reales";
  } catch (err) {
    console.error("Error en cargarComparacion:", err);
    aviso.textContent = "No se pudo cargar la comparación: " + err.message;
    aviso.classList.remove("hidden");
  }
}

cargarComparacion();
