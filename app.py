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
# 🔐 RUTAS DE AUTENTICACIÓN Y AUDITORÍA
# ==========================================

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    res = db_query("SELECT id, usuario, password_hash, rol, nombre FROM usuarios WHERE usuario = %s", (d.get('usuario'),), fetch=True)
    if res and check_password_hash(res[0][2], d.get('password')):
        session.update({'user_id': res[0][0], 'rol': res[0][3], 'nombre': res[0][4], 'modified': True})
        return jsonify({"success": True, "usuario": res[0][1], "rol": res[0][3], "nombre": res[0][4]})
    return jsonify({"success": False}), 401

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
    if session.get('rol') != 'admin': return jsonify({"message": "denegado"}), 403
    db_query("DELETE FROM usuarios WHERE id = %s", (id,))
    registrar_cambio("Eliminó Usuario", f"ID {id}")
    return jsonify({"success": True})

@app.route('/api/setup-admin', methods=['GET'])
def setup_admin():
    password_encriptada = generate_password_hash('AdminiCare2026')
    db_query("UPDATE usuarios SET password_hash = %s WHERE usuario = 'admin'", (password_encriptada,))
    return jsonify({"mensaje": "¡Contraseña de administrador actualizada y encriptada correctamente!"})


# ==========================================
# 🎫 NUEVOS CONTROLADORES MAESTROS DE SOPORTE Y TICKETS
# ==========================================

@app.route('/api/tickets', methods=['POST'])
def crear_ticket_publico():
    """Ruta pública para que los clientes envíen incidencias desde la interfaz /servicio."""
    d = request.json or {}
    empresa_id = d.get('empresa_id')
    contacto = d.get('contacto')
    asunto = d.get('asunto')
    descripcion = d.get('descripcion')
    prioridad = d.get('prioridad', 'Alta')

    if not empresa_id or not contacto or not asunto or not descripcion:
        return jsonify({"error": "Todos los campos del reporte de soporte son obligatorios"}), 400

    db_query(
        "INSERT INTO tickets_soporte (empresa_id, contacto, asunto, descripcion, prioridad) VALUES (%s, %s, %s, %s, %s)",
        (empresa_id, contacto, asunto, descripcion, prioridad)
    )
    registrar_cambio("Ticket Creado", f"Avería reportada por {contacto} (Asunto: {asunto})")
    return jsonify({"success": True, "message": "Ticket registrado con éxito"})

@app.route('/api/admin/tickets', methods=['GET'])
def listar_tickets_admin():
    """Ruta protegida para auditar e inyectar todos los tickets en la tabla administrativa."""
    if not session.get('rol'):
        return jsonify({"message": "No autorizado"}), 401

    query = '''SELECT t.id, t.empresa_id, e.nombre, t.contacto, t.asunto, t.descripcion, t.prioridad, t.estado, t.fecha 
               FROM tickets_soporte t
               JOIN empresas_recomiendan e ON t.empresa_id = e.id
               ORDER BY t.fecha DESC'''
    
    tickets_raw = db_query(query, fetch=True) or []
    resultado = [{
        "id": r[0], "empresa_id": r[1], "empresa_nombre": r[2], "contacto": r[3],
        "asunto": r[4], "descripcion": r[5], "prioridad": r[6], "estado": r[7],
        "fecha": r[8].isoformat() if hasattr(r[8], 'isoformat') else str(r[8])
    } for r in tickets_raw]
    return jsonify(resultado)

@app.route('/api/admin/tickets/<int:id>/estado', methods=['POST'])
def cambiar_estado_ticket(id):
    """Permite al administrador o personal marcar una incidencia corporativa como resuelta."""
    if not session.get('rol'):
        return jsonify({"message": "No autorizado"}), 401

    d = request.json or {}
    nuevo_estado = d.get('estado', 'Resuelto')

    db_query("UPDATE tickets_soporte SET estado = %s WHERE id = %s", (nuevo_estado, id))
    registrar_cambio("Resolvió Ticket", f"Ticket ID {id} cambiado a estado: {nuevo_estado}")
    return jsonify({"success": True})

@app.route('/api/admin/empresas-soporte', methods=['POST'])
def dar_alta_empresa_soporte():
    """Ruta privada para ingresar nuevos clientes corporativos al sistema."""
    if session.get('rol') != 'admin':
        return jsonify({"message": "Acceso denegado"}), 403

    d = request.json or {}
    nombre = d.get('nombre')
    if not nombre:
        return jsonify({"error": "Nombre requerido"}), 400

    db_query("INSERT INTO empresas_recomiendan (nombre) VALUES (%s)", (nombre,))
    registrar_cambio("Alta Empresa", f"Se dio de alta a la empresa cliente: {nombre}")
    return jsonify({"success": True})

@app.route('/api/admin/empresas-soporte/<int:id>', methods=['DELETE'])
def dar_baja_empresa_soporte(id):
    """Permite remover una empresa de la base de datos de Neon de manera permanente."""
    if session.get('rol') != 'admin':
        return jsonify({"message": "Acceso denegado"}), 403

    db_query("DELETE FROM empresas_recomiendan WHERE id = %s", (id,))
    registrar_cambio("Baja Empresa", f"Removida la empresa cliente ID {id}")
    return jsonify({"success": True})


# ==========================================
# 🛠️ RUTAS DE CONTENIDO (AUDITADAS AUTOMÁTICAMENTE)
# ==========================================

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        # Recuperación de datos
        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        parts_raw = db_query("SELECT id, nombre, imagen, url FROM socios", fetch=True) or []
        empresas_raw = db_query("SELECT id, nombre, imagen FROM empresas_recomiendan", fetch=True) or []
        objetivos_raw = db_query("SELECT id, icono, titulo, descripcion FROM clientes_objetivos", fetch=True) or []
        beneficios_raw = db_query("SELECT id, icono, titulo, descripcion FROM beneficios", fetch=True) or []
        resenas_raw = db_query("SELECT id, cliente, puesto, comentario, imagen_cliente FROM resenas", fetch=True) or [] # NUEVA
        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        
        return jsonify({
            "servicios": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in servs_raw],
            "productos": [{"id": r[0], "nombre": r[1], "precio": float(r[2]), "imagen": r[3], "categoria": r[4]} for r in prods_raw],
            "socios": [{"id": r[0], "nombre": r[1], "imagen": r[2], "url": r[3]} for r in parts_raw],
            "empresas": [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in empresas_raw],
            "objetivos": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in objetivos_raw],
            "beneficios": [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in beneficios_raw],
            "resenas": [{"id": r[0], "cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4]} for r in resenas_raw],
            "config": {r[0]: r[1] for r in config_raw}
        })
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e)}), 500

@app.route('/api/socios', methods=['POST'])
def guardar_socio():
    d = request.json or {}
    db_query("INSERT INTO socios (nombre, imagen, url) VALUES (%s, %s, %s)", 
             (d.get('nombre', 'Socio'), d.get('imagen', ''), d.get('url', '#')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios/<int:id>', methods=['GET'])
def obtener_servicio_individual(id):
    try:
        res = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios WHERE id = %s", (id,), fetch=True)
        if res:
            r = res[0]
            return jsonify({"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]})
        return jsonify({"error": "No encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/beneficios', methods=['POST'])
def guardar_beneficio():
    d = request.json or {}
    db_query("INSERT INTO beneficios (icono, titulo, descripcion) VALUES (%s, %s, %s)", (d.get('icono', 'fas fa-check'), d.get('titulo', ''), d.get('descripcion', '')))
    registrar_cambio("Guardó Tarjeta de Valor", f"Se agregó el beneficio: {d.get('titulo', 'Sin Título')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/beneficios/<int:id>', methods=['PUT'])
def editar_beneficio(id):
    d = request.json or {}
    db_query("UPDATE beneficios SET icono=%s, titulo=%s, descripcion=%s WHERE id=%s", (d.get('icono', 'fas fa-check'), d.get('titulo', ''), d.get('descripcion', ''), id))
    registrar_cambio("Editó Tarjeta de Valor", f"Se modificó el beneficio ID {id}: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/objetivos', methods=['POST'])
def guardar_objetivo():
    d = request.json or {}
    db_query("INSERT INTO clientes_objetivos (icono, titulo, descripcion) VALUES (%s, %s, %s)", (d.get('icono', 'fas fa-bullseye'), d.get('titulo', ''), d.get('descripcion', '')))
    registrar_cambio("Guardó Cliente Objetivo", f"Se registró el perfil: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/objetivos/<int:id>', methods=['PUT'])
def editar_objective(id):
    d = request.json or {}
    db_query("UPDATE clientes_objetivos SET icono=%s, titulo=%s, descripcion=%s WHERE id=%s", (d.get('icono', 'fas fa-bullseye'), d.get('titulo', ''), d.get('descripcion', ''), id))
    registrar_cambio("Editó Cliente Objetivo", f"Se actualizó el perfil ID {id}: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/recomiendan', methods=['POST'])
def guardar_empresa():
    d = request.json or {}
    db_query("INSERT INTO empresas_recomiendan (nombre, imagen) VALUES (%s, %s)", (d.get('nombre', 'Empresa'), d.get('imagen', '')))
    registrar_cambio("Guardó Empresa Coorporativa", f"Añadió la empresa: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/recomiendan/<int:id>', methods=['PUT'])
def editar_empresa(id):
    d = request.json or {}
    db_query("UPDATE empresas_recomiendan SET nombre=%s, imagen=%s WHERE id=%s", (d.get('nombre', 'Empresa'), d.get('imagen', ''), id))
    registrar_cambio("Editó Empresa Coorporativa", f"Se modificó la empresa ID {id}: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/config', methods=['POST'])
def guardar_config():
    d = request.json or {}
    claves_permitidas = ['hero_titulo', 'mision', 'vision', 'compromiso']
    for k in claves_permitidas:
        if k in d:
            db_query("INSERT INTO configuracion (clave, valor) VALUES (%s, %s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor", (k, d[k]))
            registrar_cambio("Actualizó Texto Maestro", f"Modificó la clave principal de contenido: {k}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/resenas', methods=['POST'])
def guardar_resena():
    d = request.json or {}
    db_query("INSERT INTO resenas (cliente, puesto, comentario, imagen_cliente) VALUES (%s, %s, %s, %s)", (d.get('cliente', 'Anónimo'), d.get('puesto', ''), d.get('comentario', ''), d.get('imagen_cliente', '')))
    registrar_cambio("Recibió Resaña Pública", f"El cliente {d.get('cliente', 'Anónimo')} publicó un comentario.")
    return jsonify({"mensaje": "✅"})

@app.route('/api/resenas/<int:id>', methods=['PUT'])
def editar_resena(id):
    d = request.json or {}
    db_query("UPDATE resenas SET cliente=%s, puesto=%s, comentario=%s, imagen_cliente=%s WHERE id=%s", (d.get('cliente', 'Anónimo'), d.get('puesto', ''), d.get('comentario', ''), d.get('imagen_cliente',''), id))
    registrar_cambio("Editó Reseña Interna", f"Se actualizó la reseña del ID {id}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios', methods=['POST'])
def guardar_servicio():
    d = request.json or {}
    db_query("INSERT INTO servicios (icono, titulo, descripcion, imagen, proceso, beneficios) VALUES (%s, %s, %s, %s, %s, %s)", (d.get('icono', '⚙'), d.get('titulo', ''), d.get('descripcion', ''), d.get('imagen', ''), d.get('proceso', ''), d.get('beneficios', '')))
    registrar_cambio("Creó Módulo de Servicio", f"Se agregó el servicio técnico: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/productos', methods=['POST'])
def guardar_producto():
    d = request.json or {}
    precio = d.get('precio', 0)
    try: precio = float(precio) if precio else 0
    except: precio = 0
    db_query("INSERT INTO productos (nombre, precio, imagen, categoria) VALUES (%s, %s, %s, %s)", (d.get('nombre', ''), precio, d.get('imagen', ''), d.get('categoria', 'Otros')))
    registrar_cambio("Subió Pieza/Equipo", f"Se añadió al catálogo de la tienda: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios/<int:id>', methods=['PUT'])
def editar_servicio(id):
    d = request.json or {}
    db_query("UPDATE servicios SET icono=%s, titulo=%s, descripcion=%s, imagen=%s, proceso=%s, beneficios=%s WHERE id=%s", (d.get('icono', '⚙'), d.get('titulo', ''), d.get('descripcion', ''), d.get('imagen',''), d.get('proceso', ''), d.get('beneficios', ''), id))
    registrar_cambio("Actualizó Desglose Técnico", f"Se modificó el servicio ID {id}: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/productos/<int:id>', methods=['PUT'])
def editar_producto(id):
    d = request.json or {}
    precio = d.get('precio', 0)
    try: precio = float(precio) if precio else 0
    except: precio = 0
    db_query("UPDATE productos SET nombre=%s, precio=%s, imagen=%s, categoria=%s WHERE id=%s", (d.get('nombre', ''), precio, d.get('imagen',''), d.get('categoria', 'Otros'), id))
    registrar_cambio("Modificó Precio/Pieza", f"Se actualizó el producto ID {id}: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar_item(tabla, id):
    tablas_permitidas = ['productos', 'servicios', 'socios', 'resenas', 'beneficios', 'clientes_objetivos', 'empresas_recomiendan']
    if tabla in tablas_permitidas:
        db_query(f"DELETE FROM {tabla} WHERE id = %s", (id,))
        registrar_cambio("Eliminó Contenido", f"Se borró el registro con ID {id} de la tabla '{tabla}'")
        return jsonify({"mensaje": "🗑️"})
    return jsonify({"error": "No válida"}), 400

# ==========================================
# INICIO DE LA APLICACIÓN
# ==========================================

# Garantizar que las tablas se inicialicen de inmediato al levantar el servidor
init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5001)