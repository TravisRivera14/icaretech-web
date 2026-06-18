from flask import Flask, request, jsonify, session
from flask_cors import CORS
import os
import psycopg2
import sys

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Configuración de base de datos
DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def db_query(query, params=(), fetch=False):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    res = None
    try:
        with conn.cursor() as c:
            c.execute(query, params)
            if fetch: res = c.fetchall()
            conn.commit()
    except Exception as e:
        print(f"Error en BD: {e}", file=sys.stderr)
    finally:
        conn.close()
    return res

# Inicialización de tablas
def init_db():
    queries = [
        "CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT)",
        "CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)",
        "CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT)",
        "CREATE TABLE IF NOT EXISTS beneficios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS clientes_objetivos (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT)",
        "CREATE TABLE IF NOT EXISTS socios (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT, url TEXT)",
        "CREATE TABLE IF NOT EXISTS resenas (id SERIAL PRIMARY KEY, cliente TEXT, puesto TEXT, comentario TEXT, imagen_cliente TEXT)"
    ]
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    for q in queries: c.execute(q)
    conn.commit()
    conn.close()

init_db()

# RUTA MAESTRA: El frontend consulta aquí para cargar toda la web
@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        return jsonify({
            "config": {r[0]: r[1] for r in (db_query("SELECT clave, valor FROM configuracion", fetch=True) or [])},
            "servicios": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4]} for r in (db_query("SELECT id, icono, titulo, descripcion, imagen FROM servicios", fetch=True) or [])],
            "productos": [{"id": r[0], "nombre": r[1], "precio": float(r[2] or 0), "imagen": r[3], "categoria": r[4]} for r in (db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or [])],
            "socios": [{"nombre": r[1], "imagen": r[2], "url": r[3]} for r in (db_query("SELECT id, nombre, imagen, url FROM socios", fetch=True) or [])],
            "empresas": [{"nombre": r[1], "imagen": r[2]} for r in (db_query("SELECT id, nombre, imagen FROM empresas_recomiendan", fetch=True) or [])],
            "beneficios": [{"titulo": r[2], "descripcion": r[3], "icono": r[1]} for r in (db_query("SELECT id, icono, titulo, descripcion FROM beneficios", fetch=True) or [])],
            "objetivos": [{"titulo": r[2], "descripcion": r[3], "icono": r[1]} for r in (db_query("SELECT id, icono, titulo, descripcion FROM clientes_objetivos", fetch=True) or [])],
            "resenas": [{"cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4]} for r in (db_query("SELECT id, cliente, puesto, comentario, imagen_cliente FROM resenas", fetch=True) or [])]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# RUTAS DE ADMINISTRACIÓN (Ejemplos básicos)
@app.route('/api/productos', methods=['POST'])
def guardar_producto():
    d = request.json or {}
    db_query("INSERT INTO productos (nombre, precio, imagen, categoria) VALUES (%s, %s, %s, %s)", 
             (d.get('nombre'), d.get('precio'), d.get('imagen'), d.get('categoria')))
    return jsonify({"success": True})

@app.route('/api/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar_item(tabla, id):
    db_query(f"DELETE FROM {tabla} WHERE id = %s", (id,))
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(debug=True)