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
    c.execute('''CREATE TABLE IF NOT EXISTS productos (
        id SERIAL PRIMARY KEY, 
        nombre TEXT, 
        precio NUMERIC DEFAULT 0, 
        imagen TEXT, 
        categoria TEXT DEFAULT 'Otros'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY, 
        valor TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (
        id SERIAL PRIMARY KEY, 
        icono TEXT, 
        titulo TEXT, 
        descripcion TEXT, 
        imagen TEXT,
        proceso TEXT,
        beneficios TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS socios (
        id SERIAL PRIMARY KEY, 
        nombre TEXT, 
        imagen TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS resenas (
        id SERIAL PRIMARY KEY, 
        cliente TEXT, 
        puesto TEXT, 
        comentario TEXT, 
        imagen_cliente TEXT, 
        estrellas INTEGER DEFAULT 5
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS beneficios (
        id SERIAL PRIMARY KEY,
        icono TEXT DEFAULT 'fas fa-check',
        titulo TEXT,
        descripcion TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS clientes_objetivos (
        id SERIAL PRIMARY KEY,
        icono TEXT DEFAULT 'fas fa-bullseye',
        titulo TEXT,
        descripcion TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS empresas_recomiendan (
        id SERIAL PRIMARY KEY,
        nombre TEXT,
        imagen TEXT
    )''')
    
    # 🔐 INFRAESTRUCTURA NUEVA SEGURA PARA ACCESOS Y REGISTROS
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        usuario VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        rol VARCHAR(20) NOT NULL CHECK (rol IN ('admin', 'personal')),
        nombre VARCHAR(100) NOT NULL,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial_cambios (
        id SERIAL PRIMARY KEY,
        usuario_id INT NULL,
        usuario_nombre VARCHAR(50) NOT NULL,
        accion VARCHAR(100) NOT NULL,
        detalle TEXT NOT NULL,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )''')
    
    conn.commit()
    conn.close()

# ==========================================
# 🔐 RUTAS DE AUTENTICACIÓN Y AUDITORÍA
# ==========================================

def registrar_cambio(accion, detalle):
    """Función auxiliar interna que almacena automáticamente quién modificó la landing iCare."""
    usuario_id = session.get('user_id')
    usuario_nombre = session.get('nombre', 'Sistema / Web')
    try:
        db_query(
            "INSERT INTO historial_cambios (usuario_id, usuario_nombre, accion, detalle) VALUES (%s, %s, %s, %s)",
            (usuario_id, usuario_nombre, accion, detalle)
        )
    except Exception as e:
        print(f"Error guardando log de auditoría: {e}")

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    username = d.get('usuario')
    password = d.get('password')
    
    if not username or not password:
        return jsonify({"success": False, "message": "Campos vacíos"}), 400
        
    res = db_query("SELECT id, usuario, password_hash, rol, nombre FROM usuarios WHERE usuario = %s", (username,), fetch=True)
    
    if res and check_password_hash(res[0][2], password):
        session['user_id'] = res[0][0]
        session['username'] = res[0][1]
        session['rol'] = res[0][3]
        session['nombre'] = res[0][4]
        
        session.modified = True
        
        return jsonify({
            "success": True,
            "usuario": res[0][1],
            "rol": res[0][3],
            "nombre": res[0][4]
        })
        
    return jsonify({"success": False, "message": "Usuario o contraseña incorrectos"}), 401

@app.route('/api/admin/logs', methods=['GET'])
def obtener_logs():
    if session.get('rol') != 'admin':
        return jsonify({"message": "Acceso denegado"}), 403
        
    logs_raw = db_query("SELECT fecha, usuario_nombre, accion, detalle FROM historial_cambios ORDER BY fecha DESC", fetch=True) or []
    resultado = [{"fecha": r[0].isoformat() if hasattr(r[0], 'isoformat') else str(r[0]), "usuario": r[1], "accion": r[2], "detalle": r[3]} for r in logs_raw]
    return jsonify(resultado)

@app.route('/api/admin/usuarios', methods=['GET'])
def listar_usuarios():
    if session.get('rol') != 'admin':
        return jsonify({"message": "Acceso denegado"}), 403
        
    users_raw = db_query("SELECT id, usuario, rol, nombre FROM usuarios ORDER BY id ASC", fetch=True) or []
    resultado = [{"id": r[0], "usuario": r[1], "rol": r[2], "nombre": r[3]} for r in users_raw]
    return jsonify(resultado)

@app.route('/api/admin/crear-usuario', methods=['POST'])
def crear_usuario():
    if session.get('rol') != 'admin':
        return jsonify({"message": "Acceso denegado"}), 403
        
    d = request.json or {}
    nuevo_usuario = d.get('usuario')
    password_plana = d.get('password')
    nombre_completo = d.get('nombre')
    
    if not nuevo_usuario or not password_plana or not nombre_completo:
        return jsonify({"success": False, "message": "Datos incompletos"}), 400
        
    password_encriptada = generate_password_hash(password_plana)
    
    try:
        db_query(
            "INSERT INTO usuarios (usuario, password_hash, rol, nombre) VALUES (%s, %s, 'personal', %s)",
            (nuevo_usuario, password_encriptada, nombre_completo)
        )
        registrar_cambio("Creó Usuario", f"Se registró al trabajador: {nombre_completo} ({nuevo_usuario})")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": "El usuario ya existe o es inválido"}), 400

@app.route('/api/admin/editar-usuario', methods=['POST'])
def editar_usuario():
    if session.get('rol') != 'admin':
        return jsonify({"message": "Acceso denegado"}), 403
        
    d = request.json or {}
    usuario_id = d.get('id')
    nuevo_usuario = d.get('usuario')
    nueva_password = d.get('password')
    nuevo_nombre = d.get('nombre')
    
    if not usuario_id or not nuevo_usuario or not nuevo_nombre:
        return jsonify({"success": False, "message": "Datos incompletos"}), 400

    if nueva_password and nueva_password.strip() != "":
        password_encriptada = generate_password_hash(nueva_password)
        db_query(
            "UPDATE usuarios SET usuario = %s, password_hash = %s, nombre = %s WHERE id = %s",
            (nuevo_usuario, password_encriptada, nuevo_nombre, usuario_id)
        )
    else:
        db_query(
            "UPDATE usuarios SET usuario = %s, nombre = %s WHERE id = %s",
            (nuevo_usuario, nuevo_nombre, usuario_id)
        )
        
    registrar_cambio("Modificó Usuario", f"Se actualizaron las credenciales del usuario ID {usuario_id} ({nuevo_usuario})")
    return jsonify({"success": True, "message": "Usuario modificado correctamente"})

@app.route('/api/admin/eliminar-usuario/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    if session.get('rol') != 'admin': return jsonify({"success": False, "message": "Acceso denegado"}), 403
    if session.get('user_id') == id: return jsonify({"success": False, "message": "No puedes eliminar tu propia cuenta"}), 400
    try:
        db_query("DELETE FROM usuarios WHERE id = %s", (id,))
        registrar_cambio("Eliminó Usuario", f"Se eliminó el acceso del usuario ID {id}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/setup-admin', methods=['GET'])
def setup_admin():
    password_encriptada = generate_password_hash('AdminiCare2026')
    db_query("UPDATE usuarios SET password_hash = %s WHERE usuario = 'admin'", (password_encriptada,))
    return jsonify({"mensaje": "¡Contraseña de administrador actualizada y encriptada correctamente!"})

# ==========================================
# 🛠️ RUTAS ORIGINALES AUDITADAS AUTOMÁTICAMENTE
# ==========================================

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}
        
        # ... (aquí mantienes toda tu lógica original de obtener_todo)
        
        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in servs_raw]
        
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]) if r[2] else 0.0, "imagen": r[3], "categoria": r[4]} for r in prods_raw]
        
        return jsonify({"config": config, "servicios": servs, "productos": prods})
    except Exception as e:
        return jsonify({"error": "Error interno", "detalles": str(e)}), 500

# (Nota: Debes incluir el resto de tus rutas @app.route originales de servicios, productos, etc., aquí abajo)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)