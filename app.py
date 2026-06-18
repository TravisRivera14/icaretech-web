from flask import Flask, request, jsonify, session
from flask_cors import CORS
import os
import psycopg2
from psycopg2 import pool
import sys

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Configuración de conexión (usando variable de entorno)
DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Inicializar Pool de Conexiones (mantiene hasta 10 conexiones abiertas)
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode='require')
except Exception as e:
    print(f"Error al crear el pool: {e}")

def db_query(query, params=(), fetch=False):
    conn = None
    res = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as c:
            c.execute(query, params)
            if fetch:
                res = c.fetchall()
            conn.commit()
    except Exception as e:
        print(f"Error en BD: {e}", file=sys.stderr)
        if conn: conn.rollback()
    finally:
        if conn:
            db_pool.putconn(conn)
    return res

def init_db():
    queries = [
        "CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT)",
        "CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)",
        "CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT)",
        "CREATE TABLE IF NOT EXISTS beneficios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS clientes_objetivos (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS resenas (id SERIAL PRIMARY KEY, cliente TEXT, puesto TEXT, comentario TEXT, imagen_cliente TEXT)",
        "CREATE TABLE IF NOT EXISTS socios (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT, url TEXT)",
        "CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT)"
    ]
    for q in queries:
        db_query(q)

@app.route('/api/data', methods=['GET'])
def get_data():
    try:
        return jsonify({
            "productos": [{"id": r[0], "nombre": r[1], "precio": float(r[2]), "imagen": r[3], "categoria": r[4]} for r in (db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or [])],
            "socios": [{"nombre": r[1], "imagen": r[2], "url": r[3]} for r in (db_query("SELECT id, nombre, imagen, url FROM socios", fetch=True) or [])],
            "empresas": [{"nombre": r[1], "imagen": r[2]} for r in (db_query("SELECT id, nombre, imagen FROM empresas_recomiendan", fetch=True) or [])],
            "beneficios": [{"titulo": r[2], "descripcion": r[3], "icono": r[1]} for r in (db_query("SELECT id, icono, titulo, descripcion FROM beneficios", fetch=True) or [])],
            "objetivos": [{"titulo": r[2], "descripcion": r[3], "icono": r[1]} for r in (db_query("SELECT id, icono, titulo, descripcion FROM clientes_objetivos", fetch=True) or [])],
            "resenas": [{"cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4]} for r in (db_query("SELECT id, cliente, puesto, comentario, imagen_cliente FROM resenas", fetch=True) or [])]
        })
    except Exception:
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/api/productos', methods=['POST'])
def guardar_producto():
    d = request.json or {}
    query = "INSERT INTO productos (nombre, precio, imagen, categoria) VALUES (%s, %s, %s, %s)"
    db_query(query, (d.get('nombre'), d.get('precio'), d.get('imagen'), d.get('categoria')))
    return jsonify({"status": "success"})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)