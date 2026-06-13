import sqlite3
import os

# Rutas organizadas: base de datos en carpeta 'db'
BASE_DIR = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)

# Nombre del archivo de la base de datos (ruta absoluta)
db_name = os.path.join(DB_DIR, "inventario.db")


def crear_base_de_datos():
    try:
        # Asegurar que el directorio exista y conectarse (crea el archivo si no existe)
        conexion = sqlite3.connect(db_name)
        cursor = conexion.cursor()

        # Tu esquema SQL
        script_sql = """
        CREATE TABLE IF NOT EXISTS productos (
            codigo TEXT PRIMARY KEY,
            clase TEXT,
            stock_inicial REAL,
            consumo_promedio REAL,
            consumo_minimo REAL,
            consumo_maximo REAL,
            reposicion_promedio REAL,
            frecuencia_movimiento REAL
        );

        CREATE TABLE IF NOT EXISTS inventario (
            fecha DATE,
            codigo TEXT,
            stock REAL,
            FOREIGN KEY(codigo) REFERENCES productos(codigo)
        );

        CREATE TABLE IF NOT EXISTS ordenes_restock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            fecha_pedido DATE,
            fecha_llegada DATE,
            cantidad REAL,
            estado TEXT,
            FOREIGN KEY(codigo) REFERENCES productos(codigo)
        );

        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE,
            codigo TEXT,
            tipo TEXT,
            cantidad REAL,
            stock_resultante REAL,
            FOREIGN KEY(codigo) REFERENCES productos(codigo)
        );
        """

        # Ejecutar el script
        cursor.executescript(script_sql)
        conexion.commit()
        
        print(f"¡Éxito! Base de datos creada en: {db_name}")

    except sqlite3.Error as e:
        print(f"Error al crear la base de datos: {e}")
    finally:
        if conexion:
            conexion.close()

if __name__ == "__main__":
    crear_base_de_datos()