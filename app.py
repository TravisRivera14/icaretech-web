from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')

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
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT DEFAULT 'Otros')''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT, proceso TEXT, beneficios TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, rol VARCHAR(20) NOT NULL, nombre VARCHAR(100) NOT NULL)''')
    conn.commit()
    c.close()
    conn.close()

# --- RUTAS DE ADMINISTRACIÓN ---
@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    res = db_query("SELECT id, usuario, password_hash, rol, nombre FROM usuarios WHERE usuario = %s", (d.get('usuario'),), fetch=True)
    if res and check_password_hash(res[0][2], d.get('password')):
        session.update({'user_id': res[0][0], 'rol': res[0][3], 'nombre': res[0][4]})
        return jsonify({"success": True, "rol": res[0][3], "nombre": res[0][4]})
    return jsonify({"success": False}), 401

@app.route('/api/admin/usuarios', methods=['GET'])
def listar_usuarios():
    if session.get('rol') != 'admin': return jsonify({"message": "denegado"}), 403
    users = db_query("SELECT id, usuario, rol, nombre FROM usuarios ORDER BY id ASC", fetch=True) or []
    return jsonify([{"id": r[0], "usuario": r[1], "rol": r[2], "nombre": r[3]} for r in users])

@app.route('/api/admin/crear-usuario', methods=['POST'])
def crear_usuario():
    if session.get('rol') != 'admin': return jsonify({"message": "denegado"}), 403
    d = request.json
    try:
        db_query("INSERT INTO usuarios (usuario, password_hash, rol, nombre) VALUES (%s, %s, 'personal', %s)", 
                 (d['usuario'], generate_password_hash(d['password']), d['nombre']))
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/eliminar-usuario/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    if session.get('rol') != 'admin': return jsonify({"message": "denegado"}), 403
    db_query("DELETE FROM usuarios WHERE id = %s", (id,))
    return jsonify({"success": True})

# --- TUS RUTAS ORIGINALES ---
@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        # Aquí mantienes la lógica que ya tenías para cargar productos, servicios, etc.
        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}
        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in servs_raw]
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]) if r[2] else 0.0, "imagen": r[3], "categoria": r[4]} for r in prods_raw]
        return jsonify({"config": config, "servicios": servs, "productos": prods})
    except Exception as e:
        return jsonify({"error": "Error interno", "detalles": str(e)}), 500

# (Agrega aquí abajo el resto de tus rutas @app.route originales de servicios, productos, etc.)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)