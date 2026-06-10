import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

conn = sqlite3.connect("inventario.db")

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
plt.show()