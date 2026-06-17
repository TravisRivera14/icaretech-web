from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
import sys

app = Flask(__name__)

# Configuración de seguridad
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_HTTPONLY=True
)

DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def db_query(query, params=(), fetch=False):
    conn = get_db_connection()
    res = None
    try:
        with conn.cursor() as c:
            c.execute(query, params)
            if fetch:
                res = c.fetchall()
            conn.commit()
    except Exception as e:
        print(f"Error en consulta: {e}", file=sys.stderr)
        conn.rollback()
    finally:
        conn.close()
    return res

def init_db():
    queries = [
        "CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT)",
        "CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)",
        "CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT, proceso TEXT, beneficios TEXT)",
        "CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE, password_hash VARCHAR(255), rol VARCHAR(20), nombre VARCHAR(100))",
        "CREATE TABLE IF NOT EXISTS historial_cambios (id SERIAL PRIMARY KEY, usuario_nombre TEXT, accion TEXT, detalle TEXT, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT)",
        "CREATE TABLE IF NOT EXISTS socios (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT, url TEXT)",
        "CREATE TABLE IF NOT EXISTS tickets_soporte (id SERIAL PRIMARY KEY, empresa_id INT, contacto TEXT, asunto TEXT, descripcion TEXT, prioridad TEXT, estado TEXT DEFAULT 'Abierto', fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS beneficios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS clientes_objetivos (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS resenas (id SERIAL PRIMARY KEY, cliente TEXT, puesto TEXT, comentario TEXT, imagen_cliente TEXT)"
    ]
    conn = get_db_connection()
    c = conn.cursor()
    for q in queries:
        c.execute(q)
    conn.commit()
    c.close()
    conn.close()

# Inicializar tablas al arrancar
init_db()

# ==========================================
# RUTA MAESTRA DE DATOS (Frontend Fetch)
# ==========================================
@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        return jsonify({
            "servicios": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4]} for r in (db_query("SELECT id, icono, titulo, descripcion, imagen FROM servicios", fetch=True) or [])],
            "productos": [{"id": r[0], "nombre": r[1], "precio": float(r[2] or 0), "imagen": r[3]} for r in (db_query("SELECT id, nombre, precio, imagen FROM productos", fetch=True) or [])],
            "socios": [{"id": r[0], "nombre": r[1], "imagen": r[2], "url": r[3]} for r in (db_query("SELECT id, nombre, imagen, url FROM socios", fetch=True) or [])],
            "objetivos": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in (db_query("SELECT id, icono, titulo, descripcion FROM clientes_objetivos", fetch=True) or [])],
            "beneficios": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in (db_query("SELECT id, icono, titulo, descripcion FROM beneficios", fetch=True) or [])],
            "resenas": [{"id": r[0], "cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4]} for r in (db_query("SELECT id, cliente, puesto, comentario, imagen_cliente FROM resenas", fetch=True) or [])],
            "config": {r[0]: r[1] for r in (db_query("SELECT clave, valor FROM configuracion", fetch=True) or [])}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# RUTAS DE ACCIÓN
# ==========================================
@app.route('/api/tickets', methods=['POST'])
def crear_ticket():
    d = request.json or {}
    db_query("INSERT INTO tickets_soporte (empresa_id, contacto, asunto, descripcion, prioridad) VALUES (%s, %s, %s, %s, %s)",
             (d.get('empresa_id'), d.get('contacto'), d.get('asunto'), d.get('descripcion'), d.get('prioridad')))
    return jsonify({"success": True})

@app.route('/api/resenas', methods=['POST'])
def guardar_resena():
    d = request.json or {}
    db_query("INSERT INTO resenas (cliente, puesto, comentario, imagen_cliente) VALUES (%s, %s, %s, %s)", 
             (d.get('cliente'), d.get('puesto'), d.get('comentario'), d.get('imagen_cliente')))
    return jsonify({"success": True})

# Mantén aquí tus rutas de administración (/api/login, /api/admin/...) igual que antes.

if __name__ == '__main__':
    app.run(debug=True)