from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
import psycopg2.extras
import sys

app = Flask(__name__)

# Configuración de CORS estricta
CORS(app, supports_credentials=True)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')

# Configuración de sesión para entornos HTTPS (Vercel)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_HTTPONLY=True
)

DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def db_query(query, params=(), fetch=False):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    c.close()
    conn.close()
    return res

def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        c = conn.cursor()
        # Creación de tablas base
        c.execute('''CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT DEFAULT 'Otros')''')
        c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT, proceso TEXT, beneficios TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, rol VARCHAR(20) NOT NULL CHECK (rol IN ('admin', 'personal')), nombre VARCHAR(100) NOT NULL, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_cambios (id SERIAL PRIMARY KEY, usuario_id INT NULL, usuario_nombre VARCHAR(50) NOT NULL, accion VARCHAR(100) NOT NULL, detalle TEXT NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT NOT NULL, imagen TEXT DEFAULT '')''')
        c.execute('''CREATE TABLE IF NOT EXISTS socios (id SERIAL PRIMARY KEY, nombre TEXT DEFAULT 'Socio', imagen TEXT DEFAULT '', url TEXT DEFAULT '#')''')
        c.execute('''CREATE TABLE IF NOT EXISTS tickets_soporte (id SERIAL PRIMARY KEY, empresa_id INT REFERENCES empresas_recomiendan(id) ON DELETE CASCADE, contacto VARCHAR(100) NOT NULL, asunto VARCHAR(200) NOT NULL, descripcion TEXT NOT NULL, prioridad VARCHAR(20) NOT NULL, estado VARCHAR(20) DEFAULT 'Abierto', fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # TABLAS QUE FALTABAN Y CAUSABAN EL ERROR 500
        c.execute('''CREATE TABLE IF NOT EXISTS beneficios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS clientes_objetivos (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS resenas (id SERIAL PRIMARY KEY, cliente TEXT, puesto TEXT, comentario TEXT, imagen_cliente TEXT)''')
        
        conn.commit()
        c.close()
        conn.close()
    except Exception as e:
        print(f"Error inicializando BD: {e}", file=sys.stderr)

def registrar_cambio(accion, detalle):
    usuario_id = session.get('user_id')
    usuario_nombre = session.get('nombre', 'Sistema / Web')
    try:
        db_query("INSERT INTO historial_cambios (usuario_id, usuario_nombre, accion, detalle) VALUES (%s, %s, %s, %s)", (usuario_id, usuario_nombre, accion, detalle))
    except Exception as e:
        print(f"Error log auditoría: {e}")

# ==========================================
# RUTAS
# ==========================================

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        # Recuperación segura con tablas existentes
        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        parts_raw = db_query("SELECT id, nombre, imagen, url FROM socios", fetch=True) or []
        empresas_raw = db_query("SELECT id, nombre, imagen FROM empresas_recomiendan", fetch=True) or []
        objetivos_raw = db_query("SELECT id, icono, titulo, descripcion FROM clientes_objetivos", fetch=True) or []
        beneficios_raw = db_query("SELECT id, icono, titulo, descripcion FROM beneficios", fetch=True) or []
        
        # Mapeo a diccionario
        return jsonify({
            "servicios": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in servs_raw],
            "productos": [{"id": r[0], "nombre": r[1], "precio": float(r[2]), "imagen": r[3], "categoria": r[4]} for r in prods_raw],
            "socios": [{"id": r[0], "nombre": r[1], "imagen": r[2], "url": r[3]} for r in parts_raw],
            "empresas": [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in empresas_raw],
            "objetivos": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in objetivos_raw],
            "beneficios": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in beneficios_raw]
        })
    except Exception as e:
        print(f"Error en /api/todo: {e}", file=sys.stderr)
        return jsonify({"error": str(e)}), 500

# ... [MANTÉN TODAS TUS OTRAS RUTAS IGUAL A COMO LAS TENÍAS] ...
# (Rutas de Login, Tickets, Guardar, etc.)

init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5001)