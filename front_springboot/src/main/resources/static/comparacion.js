// Gráfico comparativo: reposición reactiva vs. predictiva sobre la misma demanda.
// Consume /api/inventario/experimento (Spring -> FastAPI, resultado precalculado).

const COLOR_REACTIVA = "#dc2626";   // rojo: sin anticipación
const COLOR_PREDICTIVA = "#059669"; // verde: comprando con el modelo

let graficoComparacion = null;

function pintarResumen(data) {
  const cont = document.getElementById("resumenComparacion");
  const reactiva = data.politicas[0];
  const predictiva = data.politicas[data.politicas.length - 1];

  const tarjeta = (titulo, valor, detalle, color) =>
    '<div class="flex-1 min-w-[140px] p-4 rounded-xl border" style="border-color:' + color + '33">' +
      '<div class="text-xs uppercase tracking-wide text-gray-500">' + titulo + "</div>" +
      '<div class="text-2xl font-bold" style="color:' + color + '">' + valor + "</div>" +
      '<div class="text-xs text-gray-500 mt-1">' + detalle + "</div>" +
    "</div>";

  const diffDias = reactiva.diasAgotadoUtiles - predictiva.diasAgotadoUtiles;
  const diffPedidos = predictiva.pedidos - reactiva.pedidos;

  cont.innerHTML =
    tarjeta("Sin anticipación", reactiva.diasAgotadoUtiles.toLocaleString(),
            "días-producto sin stock", COLOR_REACTIVA) +
    tarjeta("Con el modelo", predictiva.diasAgotadoUtiles.toLocaleString(),
            diffDias.toLocaleString() + " días menos", COLOR_PREDICTIVA) +
    tarjeta("Demanda atendida",
            (reactiva.fillRate * 100).toFixed(1) + "% → " + (predictiva.fillRate * 100).toFixed(1) + "%",
            predictiva.mejoraServicioPct + "% menos faltantes", COLOR_PREDICTIVA) +
    tarjeta("Costo", "+" + diffPedidos + " pedidos",
            "stock medio " + reactiva.stockPromedio + " → " + predictiva.stockPromedio, "#64748b");
}

function pintarGrafico(data) {
  const ctx = document.getElementById("graficoComparacion");
  const reactiva = data.politicas[0];
  const predictiva = data.politicas[data.politicas.length - 1];

  if (graficoComparacion) graficoComparacion.destroy();

  graficoComparacion = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.fechas,
      datasets: [
        {
          label: reactiva.etiqueta,
          data: reactiva.serieAgotados,
          borderColor: COLOR_REACTIVA,
          backgroundColor: COLOR_REACTIVA + "20",
          fill: true,
          pointRadius: 0,
          borderWidth: 2,
        },
        {
          label: predictiva.etiqueta,
          data: predictiva.serieAgotados,
          borderColor: COLOR_PREDICTIVA,
          backgroundColor: COLOR_PREDICTIVA + "20",
          fill: true,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top" },
        tooltip: {
          callbacks: {
            label: (c) => c.dataset.label + ": " + c.parsed.y + " productos sin stock",
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          title: { display: true, text: "Productos sin stock" },
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
