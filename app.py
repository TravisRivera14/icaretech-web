from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2

app = Flask(__name__)

# Configuración de CORS con soporte estricto para credenciales y cookies en la nube
CORS(app, supports_credentials=True)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# Llave secreta obligatoria para que Flask firme las sesiones/cookies de inicio de sesión de forma segura
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')

# 🛠️ CONFIGURACIÓN CRUCIAL PARA EVITAR EL BLOQUEO DE SESIONES EN VERCEL
app.config.update(
    SESSION_COOKIE_SECURE=True,      # Obliga al navegador a enviar la cookie solo por HTTPS
    SESSION_COOKIE_SAMESITE='None',  # Permite que la cookie se comparta entre dominios cruzados
    SESSION_COOKIE_HTTPONLY=True     # Protege la cookie contra scripts maliciosos del lado del cliente
)

# Cambiamos la lectura a tu variable manual independiente libre de poolers
DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON')

if DATABASE_URL:
    # Asegurar el protocolo correcto requerido por psycopg2
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def db_query(query, params=(), fetch=False):
    # Conexión configurada con soporte SSL obligatorio para Neon
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

def init_db():
    """Crea las tablas de forma segura si no existen e inyecta columnas faltantes."""
    # Conexión configurada con soporte SSL obligatorio para Neon
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT DEFAULT 'Otros')''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT, proceso TEXT, beneficios TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, rol VARCHAR(20) NOT NULL CHECK (rol IN ('admin', 'personal')), nombre VARCHAR(100) NOT NULL, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial_cambios (id SERIAL PRIMARY KEY, usuario_id INT NULL, usuario_nombre VARCHAR(50) NOT NULL, accion VARCHAR(100) NOT NULL, detalle TEXT NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# ==========================================================
# 🔐 RUTAS DE ADMINISTRACIÓN DE USUARIOS (AGREGADO)
# ==========================================================

def registrar_cambio(accion, detalle):
    usuario_id = session.get('user_id')
    usuario_nombre = session.get('nombre', 'Sistema / Web')
    try:
        db_query("INSERT INTO historial_cambios (usuario_id, usuario_nombre, accion, detalle) VALUES (%s, %s, %s, %s)", (usuario_id, usuario_nombre, accion, detalle))
    except Exception as e:
        print(f"Error guardando log de auditoría: {e}")

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    username = d.get('usuario')
    password = d.get('password')
    res = db_query("SELECT id, usuario, password_hash, rol, nombre FROM usuarios WHERE usuario = %s", (username,), fetch=True)
    if res and check_password_hash(res[0][2], password):
        session.update({'user_id': res[0][0], 'username': res[0][1], 'rol': res[0][3], 'nombre': res[0][4], 'modified': True})
        return jsonify({"success": True, "usuario": res[0][1], "rol": res[0][3], "nombre": res[0][4]})
    return jsonify({"success": False, "message": "Credenciales incorrectas"}), 401

@app.route('/api/admin/usuarios', methods=['GET'])
def listar_usuarios():
    if session.get('rol') != 'admin': return jsonify({"message": "Acceso denegado"}), 403
    users = db_query("SELECT id, usuario, rol, nombre FROM usuarios ORDER BY id ASC", fetch=True) or []
    return jsonify([{"id": r[0], "usuario": r[1], "rol": r[2], "nombre": r[3]} for r in users])

@app.route('/api/admin/crear-usuario', methods=['POST'])
def crear_usuario():
    if session.get('rol') != 'admin': return jsonify({"message": "Acceso denegado"}), 403
    d = request.json or {}
    try:
        db_query("INSERT INTO usuarios (usuario, password_hash, rol, nombre) VALUES (%s, %s, 'personal', %s)", (d.get('usuario'), generate_password_hash(d.get('password')), d.get('nombre')))
        registrar_cambio("Creó Usuario", f"Se registró a: {d.get('nombre')}")
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/admin/editar-usuario', methods=['POST'])
def editar_usuario():
    if session.get('rol') != 'admin': return jsonify({"message": "Acceso denegado"}), 403
    d = request.json or {}
    try:
        if d.get('password'):
            db_query("UPDATE usuarios SET usuario = %s, password_hash = %s, nombre = %s WHERE id = %s", (d.get('usuario'), generate_password_hash(d.get('password')), d.get('nombre'), d.get('id')))
        else:
            db_query("UPDATE usuarios SET usuario = %s, nombre = %s WHERE id = %s", (d.get('usuario'), d.get('nombre'), d.get('id')))
        registrar_cambio("Editó Usuario", f"Se editó ID {d.get('id')}")
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/eliminar-usuario/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    if session.get('rol') != 'admin': return jsonify({"success": False, "message": "Acceso denegado"}), 403
    db_query("DELETE FROM usuarios WHERE id = %s", (id,))
    registrar_cambio("Eliminó Usuario", f"Se eliminó usuario ID {id}")
    return jsonify({"success": True})

# ==========================================================
# 🛠️ RUTAS ORIGINALES (MANTENIDAS)
# ==========================================================

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    # ... AQUÍ VA TODA TU LÓGICA ORIGINAL DE OBTENER_TODO QUE YA TENÍAS ...
    return jsonify({"status": "ok"}) 

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)