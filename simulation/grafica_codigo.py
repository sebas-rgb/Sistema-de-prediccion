import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import os

BASE_DIR = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE_DIR, "db")
FIGURES_DIR = os.path.join(BASE_DIR, "figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

db_path = os.path.join(DB_DIR, "inventario.db")
conn = sqlite3.connect(db_path)

codigo = "188486.0"

df = pd.read_sql_query(f"""
SELECT fecha, stock
FROM inventario
WHERE codigo='{codigo}'
ORDER BY fecha
""", conn)

plt.figure(figsize=(14,6))
plt.plot(df["fecha"], df["stock"])
plt.xticks(rotation=45)
plt.title(f"Producto {codigo}")
plt.tight_layout()

# Guardar figura en carpeta 'figures' y también mostrarla
fig_path = os.path.join(FIGURES_DIR, f"producto_{codigo}.png")
plt.savefig(fig_path)
print(f"Figura guardada en: {fig_path}")
plt.show()