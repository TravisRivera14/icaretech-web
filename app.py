from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_mail import Mail, Message
import os
import psycopg2

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# CONFIGURACIÓN DE CORREO
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'TU_CORREO@gmail.com'
app.config['MAIL_PASSWORD'] = 'TU_CONTRASEÑA_DE_APP'
mail = Mail(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

def db_query(query, params=(), fetch=False):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    # Inicialización de tablas
    tablas = [
        "CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT DEFAULT 'Otros')",
        "CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)",
        "CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT, proceso TEXT, beneficios TEXT)",
        "CREATE TABLE IF NOT EXISTS socios (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT)",
        "CREATE TABLE IF NOT EXISTS resenas (id SERIAL PRIMARY KEY, cliente TEXT, puesto TEXT, comentario TEXT, imagen_cliente TEXT, estrellas INTEGER DEFAULT 5)",
        "CREATE TABLE IF NOT EXISTS beneficios (id SERIAL PRIMARY KEY, icono TEXT DEFAULT 'fas fa-check', titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS clientes_objetivos (id SERIAL PRIMARY KEY, icono TEXT DEFAULT 'fas fa-bullseye', titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT)",
        "CREATE TABLE IF NOT EXISTS registro_clientes (id SERIAL PRIMARY KEY, nombre TEXT, correo TEXT, telefono TEXT, fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    ]
    for sql in tablas:
        c.execute(sql)
    conn.commit()
    conn.close()

# --- RUTAS ---

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}
        
        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in servs_raw]
        
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]) if r[2] else 0.0, "imagen": r[3], "categoria": r[4]} for r in prods_raw]
        
        parts_raw = db_query("SELECT id, nombre, imagen FROM socios", fetch=True) or []
        parts = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in parts_raw]
        
        reviews_raw = db_query("SELECT id, cliente, puesto, comentario, imagen_cliente, estrellas FROM resenas", fetch=True) or []
        reviews = [{"id": r[0], "cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4], "estrellas": r[5]} for r in reviews_raw]
        
        ben_raw = db_query("SELECT id, icono, titulo, descripcion FROM beneficios ORDER BY id ASC", fetch=True) or []
        beneficios = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in ben_raw]
        
        obj_raw = db_query("SELECT id, icono, titulo, descripcion FROM clientes_objetivos ORDER BY id ASC", fetch=True) or []
        objetivos = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in obj_raw]
        
        emp_raw = db_query("SELECT id, nombre, imagen FROM empresas_recomiendan ORDER BY id ASC", fetch=True) or []
        empresas = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in emp_raw]
        
        return jsonify({"config": config, "servicios": servs, "productos": prods, "socios": parts, "resenas": reviews, "beneficios": beneficios, "objetivos": objetivos, "empresas": empresas})
    except Exception as e: 
        return jsonify({"error": "Error interno", "detalles": str(e)}), 500

@app.route('/api/registro', methods=['POST'])
def registro_cliente():
    d = request.json or {}
    try:
        db_query("INSERT INTO registro_clientes (nombre, correo, telefono) VALUES (%s, %s, %s)", (d.get('nombre'), d.get('correo'), d.get('telefono')))
        return jsonify({"mensaje": "✅"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# (Nota: He omitido el resto de tus rutas CRUD para brevedad, 
# pero mantienen la misma lógica. Solo asegúrate de tenerlas tal cual las tenías abajo).

if __name__ == '__main__':
    # Inicialización única al arrancar
    try:
        init_db()
        print("Backend iCare Tech CR iniciado correctamente.")
    except Exception as e:
        print(f"Error crítico en BD: {e}")
        
    app.run(debug=True, port=5001)