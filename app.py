from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from functools import wraps
import os
import psycopg2
from psycopg2 import pool
import requests
import random
from datetime import datetime
import xml.etree.ElementTree as ET
import base64
import json
import hashlib
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

app = Flask(__name__)

# BLINDAJE DE PROXY: Le dice a Flask que confíe en el HTTPS de Vercel
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

CORS(app, supports_credentials=True)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')

app.config.update(
    SESSION_COOKIE_SECURE=True, 
    SESSION_COOKIE_SAMESITE='Lax', 
    SESSION_COOKIE_HTTPONLY=True
)

DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON', 'postgresql://neondb_owner:npg_rXcGY7BdMpS9@ep-green-forest-ap6dfhlf-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require')
db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)

def get_db_connection(): return db_pool.getconn()

def db_query(query, params=(), fetch=False):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute(query, params)
        res = c.fetchall() if fetch else None
        conn.commit()
        c.close()
        return res
    except Exception as e:
        print(f"Error DB: {e}")
        raise e
    finally:
        db_pool.putconn(conn)

def init_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT DEFAULT 'Otros')''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT, proceso TEXT, beneficios TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, rol VARCHAR(20) NOT NULL DEFAULT 'cliente', nombre VARCHAR(100) NOT NULL, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP, empresa VARCHAR(150), puesto VARCHAR(100), telefono VARCHAR(20), debe_cambiar_pass BOOLEAN DEFAULT FALSE, correo VARCHAR(150))''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial_cambios (id SERIAL PRIMARY KEY, usuario_id INT NULL, usuario_nombre VARCHAR(50) NOT NULL, accion VARCHAR(100) NOT NULL, detalle TEXT NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT NOT NULL, imagen TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracionhacienda (id_configuracion SERIAL PRIMARY KEY, id_empresa INT NOT NULL, cedula_juridica VARCHAR(20) DEFAULT '3101000000', hacienda_usuario_idp TEXT NOT NULL, hacienda_password_idp TEXT NOT NULL, ruta_llave_p12 TEXT NOT NULL, pin_llave_p12 VARCHAR(10) NOT NULL, ambiente_produccion BOOLEAN DEFAULT FALSE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tickets_soporte (id SERIAL PRIMARY KEY, empresa_id INT REFERENCES empresas_recomiendan(id) ON DELETE CASCADE, usuario_id INT, contacto VARCHAR(100) NOT NULL, asunto VARCHAR(200) NOT NULL, descripcion TEXT NOT NULL, prioridad VARCHAR(20) NOT NULL, estado VARCHAR(20) DEFAULT 'Abierto', whatsapp VARCHAR(20), fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS solicitudes_registro (id SERIAL PRIMARY KEY, empresa VARCHAR(150), nombre_completo VARCHAR(150), puesto VARCHAR(100), telefono VARCHAR(20), correo VARCHAR(150) UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS permisos_empresa (empresa_id INT PRIMARY KEY, facturacion BOOLEAN DEFAULT FALSE, datacenter BOOLEAN DEFAULT FALSE, inventario BOOLEAN DEFAULT FALSE, tickets BOOLEAN DEFAULT TRUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS permisos_usuario (usuario_id INT PRIMARY KEY, facturacion BOOLEAN DEFAULT FALSE, datacenter BOOLEAN DEFAULT FALSE, inventario BOOLEAN DEFAULT FALSE, tickets BOOLEAN DEFAULT TRUE)''')
    
    # NUEVAS TABLAS DE FACTURACIÓN (Ruta 2)
    c.execute('''CREATE TABLE IF NOT EXISTS clientes_facturacion (id SERIAL PRIMARY KEY, id_empresa INT NOT NULL, nombre VARCHAR(150), identificacion VARCHAR(20), tipo_identificacion VARCHAR(2), correo VARCHAR(150), telefono VARCHAR(20), fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS productos_facturacion (id SERIAL PRIMARY KEY, id_empresa INT NOT NULL, codigo_cabys VARCHAR(20), descripcion VARCHAR(200), precio_unitario NUMERIC(15,5), unidad_medida VARCHAR(10), impuesto NUMERIC(5,2), fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    c.close()
    conn.close()

    migraciones = [
        "ALTER TABLE usuarios ADD COLUMN correo VARCHAR(150)",
        "ALTER TABLE usuarios ADD COLUMN telefono VARCHAR(20)",
        "ALTER TABLE tickets_soporte ADD COLUMN usuario_id INT",
        "ALTER TABLE tickets_soporte ADD COLUMN whatsapp VARCHAR(20)",
        "ALTER TABLE tickets_soporte ADD COLUMN atendido_por VARCHAR(100) DEFAULT 'Pendiente revisión'"
    ]
    for mig in migraciones:
        try: db_query(mig)
        except Exception: pass

db_initialized = False
@app.before_request
def initialize_database():
    global db_initialized
    if not db_initialized:
        try:
            init_db()
            db_initialized = True
        except Exception as e:
            print(f"Error auto-configurando BD: {e}")

def registrar_cambio(accion, detalle):
    usuario_id = session.get('usuario_id')
    usuario_nombre = session.get('usuario', 'Sistema / Web')
    try: db_query("INSERT INTO historial_cambios (usuario_id, usuario_nombre, accion, detalle) VALUES (%s, %s, %s, %s)", (usuario_id, usuario_nombre, accion, detalle))
    except Exception: pass

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session: return jsonify({"error": "No autorizado"}), 401
        return f(*args, **kwargs)
    return decorated_function

def es_admin():
    rol = str(session.get('rol', '')).lower().strip()
    return rol in ['admin', 'personal', 'personal_admin', 'administrador']

def get_empresa_id_from_session():
    empresa_val = session.get('empresa')
    if not empresa_val: return None
    if str(empresa_val).isdigit(): return int(empresa_val)
    
    res_emp = db_query("SELECT id FROM empresas_recomiendan WHERE nombre = %s", (empresa_val,), fetch=True)
    if res_emp: return res_emp[0][0]
    return None

@app.route('/api/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if 'usuario_id' in session:
            return jsonify({
                "success": True, 
                "usuario": session.get('usuario'), 
                "empresa": session.get('empresa', 'iCareTech CR'),
                "rol": session.get('rol')
            })
        return jsonify({"success": False}), 401

    data = request.json
    usr = data.get('usuario', '').strip()
    pwd = data.get('password', '').strip()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, nombre, password_hash, rol, debe_cambiar_pass, empresa FROM usuarios WHERE LOWER(usuario) = LOWER(%s) OR LOWER(correo) = LOWER(%s) OR telefono = %s", (usr, usr, usr))
        except Exception:
            conn.rollback()
            cur.execute("SELECT id, nombre, password_hash, rol, debe_cambiar_pass, empresa FROM usuarios WHERE LOWER(usuario) = LOWER(%s)", (usr,))
            
        user = cur.fetchone()
        cur.close()
        db_pool.putconn(conn)
        if user and check_password_hash(user[2], pwd):
            session['usuario_id'] = user[0]
            session['usuario'] = user[1]
            session['rol'] = user[3]
            session['empresa'] = user[5]
            return jsonify({"success": True, "rol": user[3], "debe_cambiar_pass": user[4], "usuario_id": user[0]}), 200
        return jsonify({"success": False, "message": "Credenciales incorrectas"}), 401
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/api/admin/acceso-empresarial', methods=['POST'])
@login_required
def acceso_empresarial():
    if not es_admin(): return jsonify({"error": "Denegado"}), 403
    try:
        res = db_query("SELECT id FROM empresas_recomiendan WHERE nombre = 'iCareTech CR'", fetch=True)
        if res: 
            id_empresa = res[0][0]
        else:
            db_query("INSERT INTO empresas_recomiendan (nombre) VALUES ('iCareTech CR')")
            res = db_query("SELECT id FROM empresas_recomiendan WHERE nombre = 'iCareTech CR'", fetch=True)
            id_empresa = res[0][0]

        try: 
            db_query("INSERT INTO permisos_empresa (empresa_id, facturacion, datacenter, inventario, tickets) VALUES (%s, true, true, true, true)", (id_empresa,))
        except Exception: 
            db_query("UPDATE permisos_empresa SET facturacion=true, datacenter=true, inventario=true, tickets=true WHERE empresa_id=%s", (id_empresa,))

        u_id = session.get('usuario_id')
        try: 
            db_query("INSERT INTO permisos_usuario (usuario_id, facturacion, datacenter, inventario, tickets) VALUES (%s, true, true, true, true)", (u_id,))
        except Exception: 
            db_query("UPDATE permisos_usuario SET facturacion=true, datacenter=true, inventario=true, tickets=true WHERE usuario_id=%s", (u_id,))
        
        session['empresa'] = 'iCareTech CR'
        return jsonify({"success": True})
    except Exception as e: 
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/cliente/datos-operativos', methods=['GET'])
@login_required
def obtener_datos_operativos():
    empresa_val = session.get('empresa') 
    rol = session.get('rol')
    usuario_id = session.get('usuario_id')
    if not empresa_val: return jsonify({"error": "No asociado a empresa"}), 403
    
    try:
        id_empresa = get_empresa_id_from_session()
        if not id_empresa: return jsonify({"error": "Empresa no registrada"}), 404
            
        try: perm_emp = db_query("SELECT facturacion, datacenter, inventario, tickets FROM permisos_empresa WHERE empresa_id = %s", (id_empresa,), fetch=True)
        except: perm_emp = None
        
        try: perm_usr = db_query("SELECT facturacion, datacenter, inventario, tickets FROM permisos_usuario WHERE usuario_id = %s", (usuario_id,), fetch=True)
        except: perm_usr = None
        
        permisos_finales = {"facturacion": False, "datacenter": False, "inventario": False, "tickets": True}
        if perm_emp and perm_usr:
            permisos_finales = { "facturacion": perm_emp[0][0] and perm_usr[0][0], "datacenter": perm_emp[0][1] and perm_usr[0][1], "inventario": perm_emp[0][2] and perm_usr[0][2], "tickets": perm_emp[0][3] and perm_usr[0][3] }

        facturas = []
        if permisos_finales["facturacion"]:
            try: facturas = db_query("SELECT id, consecutivo, fecha, total_comprobante, estado_hacienda FROM Facturas WHERE id_empresa = %s", (id_empresa,), fetch=True) or []
            except: facturas = []
            
        tickets = []
        try:
            if rol == 'cliente_admin' or es_admin():
                try: tickets_raw = db_query("SELECT id, asunto, estado, prioridad, fecha, atendido_por FROM tickets_soporte WHERE empresa_id = %s ORDER BY fecha DESC", (id_empresa,), fetch=True) or []
                except: tickets_raw = db_query("SELECT id, asunto, estado, prioridad, fecha FROM tickets_soporte WHERE empresa_id = %s ORDER BY fecha DESC", (id_empresa,), fetch=True) or []
            else:
                try: tickets_raw = db_query("SELECT id, asunto, estado, prioridad, fecha, atendido_por FROM tickets_soporte WHERE usuario_id = %s ORDER BY fecha DESC", (usuario_id,), fetch=True) or []
                except: tickets_raw = db_query("SELECT id, asunto, estado, prioridad, fecha FROM tickets_soporte WHERE usuario_id = %s ORDER BY fecha DESC", (usuario_id,), fetch=True) or []
            
            for t in tickets_raw:
                atendido = t[5] if len(t) > 5 and t[5] else "Pendiente revisión"
                tickets.append({
                    "id": t[0], "asunto": t[1], "estado": t[2], "prioridad": t[3], 
                    "fecha": str(t[4]), "atendido_por": atendido
                })
        except Exception as e:
            print("Error parsing tickets:", e)
        
        return jsonify({
            "facturas": [{"id": f[0], "consecutivo": f[1], "fecha": str(f[2]), "monto": str(f[3]), "estado": f[4]} for f in facturas],
            "tickets": tickets,
            "permisos": permisos_finales,
            "rol": rol
        })
    except Exception as e: return jsonify({"error": str(e)}), 500


# ==============================================================================
#                      RUTAS DE FACTURACIÓN (CLIENTES Y PRODUCTOS)
# ==============================================================================

@app.route('/api/facturacion/clientes', methods=['GET', 'POST', 'DELETE'])
@login_required
def crud_clientes_facturacion():
    id_empresa = get_empresa_id_from_session()
    if not id_empresa: return jsonify({"error": "No asociado a empresa"}), 403

    # BLINDAJE ACTIVO: Fuerza la creación de la tabla si Vercel la omitió
    try: db_query('''CREATE TABLE IF NOT EXISTS clientes_facturacion (id SERIAL PRIMARY KEY, id_empresa INT NOT NULL, nombre VARCHAR(150), identificacion VARCHAR(20), tipo_identificacion VARCHAR(2), correo VARCHAR(150), telefono VARCHAR(20), fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    except: pass

    if request.method == 'GET':
        try:
            res = db_query("SELECT id, nombre, identificacion, tipo_identificacion, correo, telefono FROM clientes_facturacion WHERE id_empresa = %s ORDER BY nombre ASC", (id_empresa,), fetch=True) or []
            return jsonify([{"id": r[0], "nombre": r[1], "identificacion": r[2], "tipo_identificacion": r[3], "correo": r[4], "telefono": r[5]} for r in res])
        except Exception as e: return jsonify({"error": str(e)}), 500

    if request.method == 'POST':
        d = request.json
        try:
            db_query("INSERT INTO clientes_facturacion (id_empresa, nombre, identificacion, tipo_identificacion, correo, telefono) VALUES (%s, %s, %s, %s, %s, %s)", 
                     (id_empresa, d.get('nombre'), d.get('identificacion'), d.get('tipo_identificacion'), d.get('correo'), d.get('telefono')))
            return jsonify({"success": True, "message": "Cliente registrado correctamente."})
        except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

    if request.method == 'DELETE':
        d = request.json
        try:
            db_query("DELETE FROM clientes_facturacion WHERE id = %s AND id_empresa = %s", (d.get('id'), id_empresa))
            return jsonify({"success": True})
        except Exception as e: return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/facturacion/productos', methods=['GET', 'POST', 'DELETE'])
@login_required
def crud_productos_facturacion():
    id_empresa = get_empresa_id_from_session()
    if not id_empresa: return jsonify({"error": "No asociado a empresa"}), 403

    # BLINDAJE ACTIVO: Fuerza la creación de la tabla si Vercel la omitió
    try: db_query('''CREATE TABLE IF NOT EXISTS productos_facturacion (id SERIAL PRIMARY KEY, id_empresa INT NOT NULL, codigo_cabys VARCHAR(20), descripcion VARCHAR(200), precio_unitario NUMERIC(15,5), unidad_medida VARCHAR(10), impuesto NUMERIC(5,2), fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    except: pass

    if request.method == 'GET':
        try:
            res = db_query("SELECT id, codigo_cabys, descripcion, precio_unitario, unidad_medida, impuesto FROM productos_facturacion WHERE id_empresa = %s ORDER BY descripcion ASC", (id_empresa,), fetch=True) or []
            return jsonify([{"id": r[0], "codigo_cabys": r[1], "descripcion": r[2], "precio_unitario": str(r[3]), "unidad_medida": r[4], "impuesto": str(r[5])} for r in res])
        except Exception as e: return jsonify({"error": str(e)}), 500

    if request.method == 'POST':
        d = request.json
        try:
            db_query("INSERT INTO productos_facturacion (id_empresa, codigo_cabys, descripcion, precio_unitario, unidad_medida, impuesto) VALUES (%s, %s, %s, %s, %s, %s)", 
                     (id_empresa, d.get('codigo_cabys'), d.get('descripcion'), d.get('precio_unitario'), d.get('unidad_medida'), d.get('impuesto')))
            return jsonify({"success": True, "message": "Producto o servicio registrado."})
        except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

    if request.method == 'DELETE':
        d = request.json
        try:
            db_query("DELETE FROM productos_facturacion WHERE id = %s AND id_empresa = %s", (d.get('id'), id_empresa))
            return jsonify({"success": True})
        except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

# ==============================================================================


@app.route('/api/setup-admin', methods=['GET'])
def setup_admin():
    password_encriptada = generate_password_hash('AdminiCare2026')
    db_query("UPDATE usuarios SET password_hash = %s WHERE usuario = 'admin'", (password_encriptada,))
    return jsonify({"mensaje": "¡Contraseña actualizada a AdminiCare2026!"})

@app.route('/api/admin/usuarios', methods=['GET'])
@login_required
def listar_usuarios():
    if not es_admin(): return jsonify({"message": "Acceso denegado"}), 403
    try:
        users_raw = db_query("SELECT id, usuario, rol, nombre, empresa, correo, telefono FROM usuarios ORDER BY id ASC", fetch=True) or []
    except Exception:
        users_raw = db_query("SELECT id, usuario, rol, nombre, empresa, '', '' FROM usuarios ORDER BY id ASC", fetch=True) or []
    return jsonify([{"id": r[0], "usuario": r[1], "rol": r[2], "nombre": r[3], "empresa_id": r[4], "correo": r[5], "telefono": r[6]} for r in users_raw])

def error_msg_str(key, error):
    return key if key in error or "unique constraint" in error else ""

@app.route('/api/admin/crear-usuario', methods=['POST'])
@login_required
def crear_usuario():
    if not es_admin(): return jsonify({"message": "Acceso denegado"}), 403
    d = request.json or {}
    password_encriptada = generate_password_hash(d.get('password', '12345'))
    try:
        db_query("""INSERT INTO usuarios (nombre, usuario, password_hash, rol, empresa, correo, telefono) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (d.get('nombre'), d.get('usuario'), password_encriptada, d.get('rol'), d.get('empresa_id'), d.get('email'), d.get('telefono')))
        
        res = db_query("SELECT id FROM usuarios WHERE usuario = %s", (d.get('usuario'),), fetch=True)
        if res:
            try: db_query("INSERT INTO permisos_usuario (usuario_id, facturacion, datacenter, inventario, tickets) VALUES (%s, true, true, true, true)", (res[0][0],))
            except: pass

        registrar_cambio("Creó Usuario", f"Se registró a: {d.get('nombre')}")
        return jsonify({"success": True})
    except Exception as e:
        error_str = str(e).lower()
        campo_invalido = "general"
        if "usuario" in error_msg_str("usuarios_usuario_key", error_str): campo_invalido = "usuario"
        elif "correo" in error_msg_str("usuarios_correo_key", error_str) or "email" in error_str: campo_invalido = "correo"
        elif "telefono" in error_msg_str("usuarios_telefono_key", error_str) or "phone" in error_str: campo_invalido = "telefono"
        return jsonify({"success": False, "message": str(e), "campo": campo_invalido}), 400

@app.route('/api/admin/editar-usuario', methods=['POST'])
@login_required
def editar_usuario():
    if not es_admin(): return jsonify({"message": "Acceso denegado"}), 403
    d = request.json or {}
    try:
        if d.get('password') and d.get('password').strip() != "":
            db_query("UPDATE usuarios SET usuario = %s, password_hash = %s, nombre = %s, rol = %s, empresa = %s, correo = %s, telefono = %s WHERE id = %s", 
                     (d.get('usuario'), generate_password_hash(d.get('password')), d.get('nombre'), d.get('rol'), d.get('empresa_id'), d.get('correo'), d.get('telefono'), d.get('id')))
        else:
            db_query("UPDATE usuarios SET usuario = %s, nombre = %s, rol = %s, empresa = %s, correo = %s, telefono = %s WHERE id = %s", 
                     (d.get('usuario'), d.get('nombre'), d.get('rol'), d.get('empresa_id'), d.get('correo'), d.get('telefono'), d.get('id')))
        registrar_cambio("Modificó Usuario", f"Actualizadas credenciales de {d.get('usuario')}")
        return jsonify({"success": True})
    except Exception as e:
        error_str = str(e).lower()
        campo_invalido = "general"
        if "usuario" in error_msg_str("usuarios_usuario_key", error_str): campo_invalido = "usuario"
        elif "correo" in error_msg_str("usuarios_correo_key", error_str) or "email" in error_str: campo_invalido = "correo"
        elif "telefono" in error_msg_str("usuarios_telefono_key", error_str) or "phone" in error_str: campo_invalido = "telefono"
        return jsonify({"success": False, "message": str(e), "campo": campo_invalido}), 400

@app.route('/api/admin/eliminar-usuario/<int:id>', methods=['DELETE'])
@login_required
def eliminar_usuario(id):
    if not es_admin(): return jsonify({"message": "denegado"}), 403
    try:
        try: db_query("UPDATE tickets_soporte SET usuario_id = NULL WHERE usuario_id = %s", (id,))
        except Exception: pass
        
        try: db_query("DELETE FROM permisos_usuario WHERE usuario_id = %s", (id,))
        except Exception: pass
        
        db_query("DELETE FROM usuarios WHERE id = %s", (id,))
        registrar_cambio("Eliminó Usuario", f"ID {id}")
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/logs', methods=['GET'])
@login_required
def get_logs():
    if not es_admin(): return jsonify({"message": "Denegado"}), 403
    try:
        logs = db_query("SELECT fecha, usuario_nombre, accion, detalle FROM historial_cambios ORDER BY fecha DESC LIMIT 100", fetch=True) or []
        return jsonify([{"fecha": str(l[0]), "usuario": l[1], "accion": l[2], "detalle": l[3]} for l in logs])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/operaciones/empresa/<int:empresa_id>', methods=['GET'])
@login_required
def get_permisos_empresa(empresa_id):
    if not es_admin(): return jsonify({"error": "Denegado"}), 403
    try: p = db_query("SELECT facturacion, datacenter, inventario, tickets FROM permisos_empresa WHERE empresa_id = %s", (empresa_id,), fetch=True)
    except: p = None
    if p: return jsonify({"facturacion": p[0][0], "datacenter": p[0][1], "inventario": p[0][2], "tickets": p[0][3]})
    
    try: db_query("INSERT INTO permisos_empresa (empresa_id, facturacion, datacenter, inventario, tickets) VALUES (%s, false, false, false, true)", (empresa_id,))
    except: pass
    return jsonify({"facturacion": False, "datacenter": False, "inventario": False, "tickets": True})

@app.route('/api/admin/operaciones/empresa', methods=['POST'])
@login_required
def save_permisos_empresa():
    if not es_admin(): return jsonify({"error": "Denegado"}), 403
    d = request.json
    try: db_query("UPDATE permisos_empresa SET facturacion=%s, datacenter=%s, inventario=%s, tickets=%s WHERE empresa_id=%s", (d.get('facturacion'), d.get('datacenter'), d.get('inventario'), d.get('tickets'), d.get('empresa_id')))
    except: pass
    return jsonify({"success": True})

@app.route('/api/admin/operaciones/usuarios/<int:empresa_id>', methods=['GET'])
@login_required
def get_permisos_usuarios_empresa(empresa_id):
    if not es_admin(): return jsonify({"error": "Denegado"}), 403
    res_emp = db_query("SELECT nombre FROM empresas_recomiendan WHERE id = %s", (empresa_id,), fetch=True)
    nombre_empresa = res_emp[0][0] if res_emp else ""
    
    users = db_query("SELECT id, nombre, rol FROM usuarios WHERE empresa = %s OR empresa = %s", (str(empresa_id), nombre_empresa), fetch=True) or []
    lista = []
    for u in users:
        u_id = u[0]
        try: p = db_query("SELECT facturacion, datacenter, inventario, tickets FROM permisos_usuario WHERE usuario_id = %s", (u_id,), fetch=True)
        except: p = None
        
        if not p:
            try: db_query("INSERT INTO permisos_usuario (usuario_id, facturacion, datacenter, inventario, tickets) VALUES (%s, true, true, true, true)", (u_id,))
            except: pass
            p = [(True, True, True, True)]
        lista.append({"id": u_id, "nombre": u[1], "rol": u[2], "permisos": {"facturacion": p[0][0], "datacenter": p[0][1], "inventario": p[0][2], "tickets": p[0][3]}})
    return jsonify(lista)

@app.route('/api/admin/operaciones/usuario', methods=['POST'])
@login_required
def save_permisos_usuario():
    if not es_admin(): return jsonify({"error": "Denegado"}), 403
    d = request.json
    try: db_query("UPDATE permisos_usuario SET facturacion=%s, datacenter=%s, inventario=%s, tickets=%s WHERE usuario_id=%s", (d.get('facturacion'), d.get('datacenter'), d.get('inventario'), d.get('tickets'), d.get('usuario_id')))
    except: pass
    return jsonify({"success": True})

def obtener_oauth_token_hacienda(id_empresa):
    res = db_query("""SELECT hacienda_usuario_idp, hacienda_password_idp, ambiente_produccion FROM configuracionhacienda WHERE id_empresa = %s""", (id_empresa,), fetch=True)
    if not res: raise Exception(f"La empresa con ID {id_empresa} no tiene configuradas sus credenciales de Hacienda.")
    usuario_idp = res[0][0]; password_idp = res[0][1]; ambiente_produccion = res[0][2]

    url_auth = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token" if ambiente_produccion else "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token"

    payload = {'grant_type': 'password', 'client_id': 'api-stag' if not ambiente_produccion else 'api-prod', 'username': usuario_idp, 'password': password_idp}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    try:
        response = requests.post(url_auth, data=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            datos_token = response.json()
            return {"success": True, "access_token": datos_token.get("access_token"), "expires_in": datos_token.get("expires_in"), "refresh_token": datos_token.get("refresh_token")}
        else:
            return {"success": False, "status_code": response.status_code, "error_detalle": response.text}
    except Exception as e:
        return {"success": False, "error_detalle": f"No se pudo conectar con Hacienda: {str(e)}"}

def firmar_xml_hacienda(xml_sin_firmar, p12_b64, pin):
    try:
        p12_data = base64.b64decode(p12_b64)
        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
            p12_data, 
            pin.encode(),
            backend=default_backend()
        )
        cert_der = certificate.public_bytes(serialization.Encoding.DER)
        cert_b64 = base64.b64encode(cert_der).decode('utf-8')
        signature_template = f"""
        <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="Signature-iCare">
            <ds:SignedInfo>
                <ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
                <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
                <ds:Reference Id="Reference-iCare" URI="">
                    <ds:Transforms>
                        <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
                    </ds:Transforms>
                    <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                    <ds:DigestValue>... (Hash a generar) ...</ds:DigestValue>
                </ds:Reference>
            </ds:SignedInfo>
            <ds:SignatureValue>... (Firma RSA) ...</ds:SignatureValue>
            <ds:KeyInfo>
                <ds:X509Data>
                    <ds:X509Certificate>{cert_b64}</ds:X509Certificate>
                </ds:X509Data>
            </ds:KeyInfo>
        </ds:Signature>
        """
        xml_firmado = xml_sin_firmar.replace("</FacturaElectronica>", f"{signature_template}</FacturaElectronica>")
        return xml_firmado
    except Exception as e:
        raise Exception(f"Fallo al firmar criptográficamente el XML: {str(e)}")

def enviar_factura_hacienda(id_empresa, datos_xml, xml_firmado_o_raw):
    token_data = obtener_oauth_token_hacienda(id_empresa)
    if not token_data["success"]: return {"success": False, "message": "Error autenticando con Hacienda: " + token_data.get("error_detalle", "")}
    token = token_data["access_token"]
    payload = {
        "clave": datos_xml['clave'], "fecha": datetime.now().isoformat(),
        "emisor": {"tipoIdentificacion": "02", "numeroIdentificacion": datos_xml['emisor_cedula']},
        "receptor": {"tipoIdentificacion": "01", "numeroIdentificacion": datos_xml['cliente_cedula']},
        "comprobanteXml": base64.b64encode(xml_firmado_o_raw.encode()).decode()
    }
    url_recepcion = "https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        resp = requests.post(url_recepcion, json=payload, headers=headers)
        if resp.status_code == 202: return {"success": True}
        else: return {"success": False, "message": f"Hacienda respondió: {resp.status_code} - {resp.text}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.route('/api/admin/facturacion/probar-conexion', methods=['GET'])
@login_required
def probar_conexion_hacienda():
    id_empresa_actual = get_empresa_id_from_session()
    if not id_empresa_actual:
        return jsonify({"status": "Error", "mensaje": "Usuario no tiene empresa asignada."}), 400
        
    try:
        resultado = obtener_oauth_token_hacienda(id_empresa_actual)
        if resultado["success"]: 
            return jsonify({"status": "Conexión Exitosa", "mensaje": "Autenticado correctamente con Hacienda.", "token": resultado["access_token"][:15] + "..."})
        else: 
            return jsonify({"status": "Error de Autenticación", "mensaje": "Hacienda rechazó las credenciales.", "detalles_tecnicos": resultado}), 400
    except Exception as e:
        return jsonify({"status": "Error Interno", "error": str(e)}), 500

@app.route('/api/admin/configuracion-hacienda', methods=['POST'])
@login_required
def guardar_configuracion_hacienda():
    rol = str(session.get('rol', '')).lower().strip()
    if rol not in ['admin', 'personal', 'personal_admin', 'cliente_admin']:
        return jsonify({"message": "Acceso denegado"}), 403
        
    usuario_idp = request.form.get('usuario_idp')
    password_idp = request.form.get('password_idp')
    pin_p12 = request.form.get('pin_p12')
    ambiente = request.form.get('ambiente')
    ambiente_produccion = True if ambiente in ['true', 'on', True] else False
    archivo_p12 = request.files.get('archivo_p12')
    
    id_empresa_actual = get_empresa_id_from_session()
    if not id_empresa_actual:
        return jsonify({"success": False, "message": "Tu cuenta no está vinculada a una empresa."}), 400

    if not usuario_idp or not password_idp or not pin_p12 or not archivo_p12:
        return jsonify({"success": False, "message": "Todos los campos de Hacienda son requeridos"}), 400

    try:
        contenido_binario = archivo_p12.read()
        p12_base64 = base64.b64encode(contenido_binario).decode('utf-8')
        existe = db_query("SELECT id_configuracion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa_actual,), fetch=True)
        if existe:
            db_query("""UPDATE configuracionhacienda SET hacienda_usuario_idp = %s, hacienda_password_idp = %s, ruta_llave_p12 = %s, pin_llave_p12 = %s, ambiente_produccion = %s WHERE id_empresa = %s""", (usuario_idp, password_idp, p12_base64, pin_p12, ambiente_produccion, id_empresa_actual))
        else:
            db_query("""INSERT INTO configuracionhacienda (id_empresa, hacienda_usuario_idp, hacienda_password_idp, ruta_llave_p12, pin_llave_p12, ambiente_produccion) VALUES (%s, %s, %s, %s, %s, %s)""", (id_empresa_actual, usuario_idp, password_idp, p12_base64, pin_p12, ambiente_produccion))
        registrar_cambio("Configuró Hacienda", f"Credenciales actualizadas para Empresa ID: {id_empresa_actual}")
        return jsonify({"success": True, "message": "Configuración de Hacienda guardada correctamente en el servidor."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error interno: {str(e)}"}), 500

@app.route('/api/admin/configuracion-hacienda/verificar', methods=['GET'])
@login_required
def verificar_configuracion_hacienda():
    if not es_admin(): return jsonify({"message": "Acceso denegado"}), 403
    id_empresa = request.args.get('id_empresa', 1)
    res = db_query("SELECT hacienda_usuario_idp, ambiente_produccion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    if res: return jsonify({"configurado": True, "usuario_idp": res[0][0], "ambiente": "Producción" if res[0][1] else "Pruebas / Sandbox"})
    return jsonify({"configurado": False})

def calcular_clave_50_digitos(cedula_emisor, consecutivo, situacion="1"):
    ahora = datetime.now()
    dia = ahora.strftime("%d"); mes = ahora.strftime("%m"); ano = ahora.strftime("%y")
    cedula_limpia = "".join(filter(str.isdigit, str(cedula_emisor)))
    cedula_12 = cedula_limpia.zfill(12)
    codigo_seguridad = "".join([str(random.randint(0, 9)) for _ in range(8)])
    clave = f"506{dia}{mes}{ano}{cedula_12}{consecutivo}{situacion}{codigo_seguridad}"
    if len(clave) != 50: raise Exception(f"Error crítico en el cálculo de la clave. Longitud obtenida: {len(clave)} de 50.")
    return clave

def generar_xml_factura_44(datos_factura, lineas_detalle):
    NS_FACTURA = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturelectronica"
    root = ET.Element("FacturaElectronica", {"xmlns": NS_FACTURA, "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance", "xsi:schemaLocation": f"{NS_FACTURA} https://www.hacienda.go.cr/ATV/ComprobanteElectronico/v4.4/facturelectronica.xsd"})
    ET.SubElement(root, "Clave").text = datos_factura['clave']
    ET.SubElement(root, "CodigoActividad").text = datos_factura.get('codigo_actividad', '620201')
    ET.SubElement(root, "NumeroConsecutivo").text = datos_factura['consecutivo']
    ET.SubElement(root, "FechaEmision").text = datetime.now().isoformat()[:-3] + "-06:00"
    emisor = ET.SubElement(root, "Emisor")
    ET.SubElement(emisor, "Nombre").text = datos_factura['emisor_nombre']
    id_emisor = ET.SubElement(emisor, "Identificacion")
    ET.SubElement(id_emisor, "Tipo").text = datos_factura.get('emisor_tipo_cedula', '02')
    ET.SubElement(id_emisor, "Numero").text = datos_factura['emisor_cedula']
    ET.SubElement(emisor, "CorreoElectronico").text = datos_factura.get('emisor_correo', 'soporte@icartech.cr')
    receptor = ET.SubElement(root, "Receptor")
    ET.SubElement(receptor, "Nombre").text = datos_factura['cliente_nombre']
    id_receptor = ET.SubElement(receptor, "Identificacion")
    ET.SubElement(id_receptor, "Tipo").text = datos_factura.get('cliente_tipo_cedula', '01')
    ET.SubElement(id_receptor, "Numero").text = datos_factura['cliente_cedula']
    ET.SubElement(receptor, "CorreoElectronico").text = datos_factura.get('cliente_correo')
    ET.SubElement(root, "CondicionVenta").text = datos_factura.get('condicion_venta', '01')
    ET.SubElement(root, "MedioPago").text = datos_factura.get('medio_pago', '04')
    detalle_nodo = ET.SubElement(root, "DetalleServicio")
    total_serv_gravados = 0.0; total_iva = 0.0
    for idx, linea in enumerate(lineas_detalle, start=1):
        linea_nodo = ET.SubElement(detalle_nodo, "LineaDetalle")
        ET.SubElement(linea_nodo, "NumeroLinea").text = str(idx)
        ET.SubElement(linea_nodo, "Codigo").text = linea['codigo_cabys']
        ET.SubElement(linea_nodo, "Cantidad").text = f"{float(linea['cantidad']):.3f}"
        ET.SubElement(linea_nodo, "UnidadMedida").text = linea.get('unidad_medida', 'Sp')
        ET.SubElement(linea_nodo, "Detalle").text = linea['descripcion']
        ET.SubElement(linea_nodo, "PrecioUnitario").text = f"{float(linea['precio_unitario']):.5f}"
        ET.SubElement(linea_nodo, "MontoTotal").text = f"{float(linea['monto_total']):.5f}"
        ET.SubElement(linea_nodo, "SubTotal").text = f"{float(linea['monto_total']):.5f}"
        monto_impuesto = float(linea['monto_total']) * 0.13
        total_serv_gravados += float(linea['monto_total'])
        total_iva += monto_impuesto
        impuesto_nodo = ET.SubElement(linea_nodo, "Impuesto")
        ET.SubElement(impuesto_nodo, "Codigo").text = "01"
        ET.SubElement(impuesto_nodo, "CodigoTarifa").text = "08"
        ET.SubElement(impuesto_nodo, "Tarifa").text = "13.00"
        ET.SubElement(impuesto_nodo, "Monto").text = f"{monto_impuesto:.5f}"
        ET.SubElement(linea_nodo, "MontoTotalLinea").text = f"{(float(linea['monto_total']) + monto_impuesto):.5f}"
    resumen = ET.SubElement(root, "ResumenFactura")
    ET.SubElement(resumen, "CodigoTipoMoneda").text = datos_factura.get('moneda', 'CRC')
    ET.SubElement(resumen, "TipoCambio").text = "1.00000"
    ET.SubElement(resumen, "TotalServGravados").text = f"{total_serv_gravados:.5f}"
    ET.SubElement(resumen, "TotalServExentos").text = "0.00000"
    ET.SubElement(resumen, "TotalMercanciasGravadas").text = "0.00000"
    ET.SubElement(resumen, "TotalMercanciasExentas").text = "0.00000"
    ET.SubElement(resumen, "TotalGravado").text = f"{total_serv_gravados:.5f}"
    ET.SubElement(resumen, "TotalExento").text = "0.00000"
    ET.SubElement(resumen, "TotalVenta").text = f"{total_serv_gravados:.5f}"
    ET.SubElement(resumen, "TotalDescuentos").text = "0.00000"
    ET.SubElement(resumen, "TotalVentaNeto").text = f"{total_serv_gravados:.5f}"
    ET.SubElement(resumen, "TotalImpuesto").text = f"{total_iva:.5f}"
    ET.SubElement(resumen, "TotalComprobante").text = f"{(total_serv_gravados + total_iva):.5f}"
    return ET.tostring(root, encoding="utf-8").decode("utf-8")

@app.route('/api/facturacion/emitir', methods=['POST'])
@login_required
def emitir_factura_electronica_api():
    d = request.json or {}
    cliente_id = d.get('cliente_id')
    condicion_venta = d.get('condicion_venta', '01')
    medio_pago = d.get('medio_pago', '04')
    lineas_frontend = d.get('lineas', [])
    id_empresa_actual = get_empresa_id_from_session() 

    if not cliente_id or not lineas_frontend or not id_empresa_actual:
        return jsonify({"success": False, "message": "Faltan datos esenciales o empresa no asociada."}), 400

    try:
        res_config = db_query("SELECT ruta_llave_p12, pin_llave_p12 FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa_actual,), fetch=True)
        if not res_config: return jsonify({"success": False, "message": "No hay llave criptográfica configurada. Ve a Configuración de Hacienda."}), 400
        p12_b64, pin_p12 = res_config[0]

        res_emisor = db_query("SELECT cedula_juridica, nombre_empresa, correo FROM empresa WHERE id_empresa = %s", (id_empresa_actual,), fetch=True)
        if not res_emisor: return jsonify({"success": False, "message": "Empresa emisora no registrada en la tabla de facturación"}), 400
        res_cliente = db_query("SELECT identificacion, nombre, correo FROM clientes_facturacion WHERE id = %s", (cliente_id,), fetch=True)
        if not res_cliente: return jsonify({"success": False, "message": "El cliente no existe"}), 400
        
        emisor_datos = {"cedula": res_emisor[0][0], "nombre": res_emisor[0][1], "correo": res_emisor[0][2]}
        cliente_datos = {"cedula": res_cliente[0][0], "nombre": res_cliente[0][1], "correo": res_cliente[0][2]}
        consecutivo_sistema = "0010000101" + datetime.now().strftime("%H%M%S").zfill(10)
        clave_50 = calcular_clave_50_digitos(emisor_datos["cedula"], consecutivo_sistema)

        total_serv_gravados = sum(float(l['monto_total']) for l in lineas_frontend)
        total_iva = total_serv_gravados * 0.13
        total_comprobante = total_serv_gravados + total_iva

        db_query("""INSERT INTO Facturas (Id_Empresa, Id_Cliente, Consecutivo, Clave_50_Digitos, Condicion_Venta, Medio_Pago, Total_Servicios_Gravados, Total_Impuesto, Total_Comprobante, Estado_Hacienda) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendiente')""", (id_empresa_actual, cliente_id, consecutivo_sistema, clave_50, condicion_venta, medio_pago, total_serv_gravados, total_iva, total_comprobante))

        datos_xml_maestro = {'clave': clave_50, 'consecutivo': consecutivo_sistema, 'emisor_nombre': emisor_datos["nombre"], 'emisor_cedula': emisor_datos["cedula"], 'emisor_correo': emisor_datos["correo"], 'cliente_nombre': cliente_datos["nombre"], 'cliente_cedula': cliente_datos["cedula"], 'cliente_correo': cliente_datos["correo"], 'condicion_venta': condicion_venta, 'medio_pago': medio_pago}
        
        xml_generado_crudo = generar_xml_factura_44(datos_xml_maestro, lineas_frontend)
        xml_firmado_listo = firmar_xml_hacienda(xml_generado_crudo, p12_b64, pin_p12)
        resultado_envio = enviar_factura_hacienda(id_empresa_actual, datos_xml_maestro, xml_firmado_listo)

        if resultado_envio["success"]: return jsonify({"success": True, "message": "Factura procesada con éxito", "clave": clave_50, "consecutivo": consecutivo_sistema})
        else:
            db_query("UPDATE Facturas SET Estado_Hacienda = 'Rechazado', Mensaje_Hacienda = %s WHERE Clave_50_Digitos = %s", (resultado_envio["message"], clave_50))
            return jsonify({"success": False, "message": resultado_envio["message"]}), 400
    except Exception as e:
        registrar_cambio("Error Facturación", f"Fallo crítico emitiendo comprobante: {str(e)}")
        return jsonify({"success": False, "message": f"Error interno: {str(e)}"}), 500

@app.route('/api/admin/solicitudes', methods=['GET'])
def listar_solicitudes():
    res = db_query("SELECT id, empresa, nombre_completo, correo FROM solicitudes_registro", fetch=True) or []
    return jsonify([{"id": r[0], "empresa": r[1], "nombre": r[2], "correo": r[3]} for r in res])

@app.route('/api/admin/aprobar_solicitud', methods=['POST'])
def aprobar_solicitud():
    sol_id = request.json.get('id')
    try:
        sol = db_query("SELECT empresa, nombre_completo, correo FROM solicitudes_registro WHERE id = %s", (sol_id,), fetch=True)
        if not sol: return jsonify({"success": False}), 404
        emp, nom, corr = sol[0]
        db_query("INSERT INTO usuarios (usuario, password_hash, rol, nombre, empresa, correo, debe_cambiar_pass) VALUES (%s, %s, 'cliente', %s, %s, %s, TRUE)", (corr, generate_password_hash('iCare2026_Cambiar'), nom, emp, corr))
        db_query("DELETE FROM solicitudes_registro WHERE id = %s", (sol_id,))
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/eliminar-varios', methods=['POST'])
def eliminar_varios():
    data = request.json
    tabla = data.get('tabla')
    ids = tuple(data.get('ids', []))
    db_query(f"DELETE FROM {tabla} WHERE id IN %s", (ids,))
    return jsonify({"success": True})

@app.route('/api/registro_corporativo', methods=['POST'])
def registro_corporativo():
    data = request.json
    try:
        db_query("""INSERT INTO solicitudes_registro (empresa, nombre_completo, puesto, telefono, correo) VALUES (%s, %s, %s, %s, %s)""", (data.get('empresa'), data.get('nombre'), data.get('puesto'), data.get('telefono'), data.get('correo')))
        return jsonify({"success": True}), 201
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}
        if 'hero_titulo' not in config: db_query("INSERT INTO configuracion (clave, valor) VALUES ('hero_titulo', 'Servicio Técnico Profesional') ON CONFLICT DO NOTHING")
        if 'mision' not in config: db_query("INSERT INTO configuracion (clave, valor) VALUES ('mision', 'Brindar soporte técnico especializado con honestidad y excelencia.') ON CONFLICT DO NOTHING")
        if 'vision' not in config: db_query("INSERT INTO configuracion (clave, valor) VALUES ('vision', 'Ser la empresa líder en soluciones tecnológicas y seguridad en Costa Rica.') ON CONFLICT DO NOTHING")
        if 'compromiso' not in config: db_query("INSERT INTO configuracion (clave, valor) VALUES ('compromiso', 'Aseguramos la continuidad operativa de tu negocio mediante respuestas rápidas, acuerdos de nivel de servicio (SLA) eficientes y soporte de alta disponibilidad.') ON CONFLICT DO NOTHING")

        beneficios_existentes = db_query("SELECT COUNT(*) FROM beneficios", fetch=True)
        if beneficios_existentes and beneficios_existentes[0][0] == 0:
            ventajas_defecto = [("Técnicos Certificados", "Tu infraestructura manipulada por profesionales.", "fas fa-user-check"), ("Repuestos Originales", "Componentes genuinos.", "fas fa-shield-alt"), ("Transparencia", "Sin costos ocultos.", "fas fa-handshake")]
            for titulo, desc, icono in ventajas_defecto: db_query("INSERT INTO beneficios (titulo, descripcion, icono) VALUES (%s, %s, %s)", (titulo, desc, icono))

        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}

        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in servs_raw]
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]) if r[2] else 0.0, "imagen": r[3], "categoria": r[4]} for r in prods_raw]
        parts_raw = db_query("SELECT id, nombre, imagen FROM socios", fetch=True) or []
        parts = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in parts_raw]
        reviews_raw = db_query("SELECT id, cliente, puesto, comentario, imagen_cliente FROM resenas", fetch=True) or []
        reviews = [{"id": r[0], "cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4]} for r in reviews_raw]
        ben_raw = db_query("SELECT id, icono, titulo, descripcion FROM beneficios ORDER BY id ASC", fetch=True) or []
        beneficios = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in ben_raw]
        obj_raw = db_query("SELECT id, icono, titulo, descripcion FROM clientes_objetivos ORDER BY id ASC", fetch=True) or []
        objetivos = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in obj_raw]
        emp_raw = db_query("SELECT id, nombre, imagen FROM empresas_recomiendan ORDER BY id ASC", fetch=True) or []
        empresas = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in emp_raw]

        return jsonify({"config": config, "servicios": servs, "productos": prods, "socios": parts, "resenas": reviews, "beneficios": beneficios, "objetivos": objetivos, "empresas": empresas})
    except Exception as e: return jsonify({"error": "Error interno", "detalles": str(e)}), 500

@app.route('/api/servicios/<int:id>', methods=['GET'])
def obtener_servicio_individual(id):
    try:
        res = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios WHERE id = %s", (id,), fetch=True)
        if res:
            r = res[0]
            return jsonify({"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]})
        return jsonify({"error": "No encontrado"}), 404
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/beneficios', methods=['POST'])
@login_required
def guardar_beneficio():
    d = request.json or {}
    db_query("INSERT INTO beneficios (icono, titulo, descripcion) VALUES (%s, %s, %s)", (d.get('icono', 'fas fa-check'), d.get('titulo', ''), d.get('descripcion', '')))
    registrar_cambio("Guardó Tarjeta de Valor", f"Se agregó el beneficio: {d.get('titulo', 'Sin Título')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/beneficios/<int:id>', methods=['PUT'])
@login_required
def editar_beneficio(id):
    d = request.json or {}
    db_query("UPDATE beneficios SET icono=%s, titulo=%s, descripcion=%s WHERE id=%s", (d.get('icono', 'fas fa-check'), d.get('titulo', ''), d.get('descripcion', ''), id))
    registrar_cambio("Editó Tarjeta de Valor", f"Se modificó el beneficio ID {id}: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/objetivos', methods=['POST'])
@login_required
def guardar_objetivo():
    d = request.json or {}
    db_query("INSERT INTO clientes_objetivos (icono, titulo, descripcion) VALUES (%s, %s, %s)", (d.get('icono', 'fas fa-bullseye'), d.get('titulo', ''), d.get('descripcion', '')))
    registrar_cambio("Guardó Cliente Objetivo", f"Se registró el perfil: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/objetivos/<int:id>', methods=['PUT'])
@login_required
def editar_objective(id):
    d = request.json or {}
    db_query("UPDATE clientes_objetivos SET icono=%s, titulo=%s, descripcion=%s WHERE id=%s", (d.get('icono', 'fas fa-bullseye'), d.get('titulo', ''), d.get('descripcion', ''), id))
    registrar_cambio("Editó Cliente Objetivo", f"Se actualizó el perfil ID {id}: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/recomiendan', methods=['POST'])
@login_required
def guardar_empresa():
    d = request.json or {}
    db_query("INSERT INTO empresas_recomiendan (nombre, imagen) VALUES (%s, %s)", (d.get('nombre', 'Empresa'), d.get('imagen', '')))
    registrar_cambio("Agregó Cliente Corporativo", f"Añadió la empresa: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/recomiendan/<int:id>', methods=['PUT'])
@login_required
def editar_empresa(id):
    d = request.json or {}
    db_query("UPDATE empresas_recomiendan SET nombre=%s, imagen=%s WHERE id=%s", (d.get('nombre', 'Empresa'), d.get('imagen', ''), id))
    registrar_cambio("Editó Cliente Corporativo", f"Se modificó la empresa ID {id}: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/config', methods=['POST'])
@login_required
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
    registrar_cambio("Recibió Reseña Pública", f"El cliente {d.get('cliente', 'Anónimo')} publicó un comentario.")
    return jsonify({"mensaje": "✅"})

@app.route('/api/resenas/<int:id>', methods=['PUT'])
@login_required
def editar_resena(id):
    d = request.json or {}
    db_query("UPDATE resenas SET cliente=%s, puesto=%s, comentario=%s, imagen_cliente=%s WHERE id=%s", (d.get('cliente', 'Anónimo'), d.get('puesto', ''), d.get('comentario', ''), d.get('imagen_cliente',''), id))
    registrar_cambio("Editó Reseña Interna", f"Se actualizó la reseña del ID {id}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/socios', methods=['POST'])
@login_required
def guardar_socio():
    d = request.json or {}
    db_query("INSERT INTO socios (nombre, imagen) VALUES (%s, %s)", (d.get('nombre', 'Socio'), d.get('imagen', '')))
    registrar_cambio("Añadió Socio Comercial", f"Se registró el socio: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios', methods=['POST'])
@login_required
def guardar_servicio():
    d = request.json or {}
    db_query("INSERT INTO servicios (icono, titulo, descripcion, imagen, proceso, beneficios) VALUES (%s, %s, %s, %s, %s, %s)", (d.get('icono', '⚙'), d.get('titulo', ''), d.get('descripcion', ''), d.get('imagen', ''), d.get('proceso', ''), d.get('beneficios', '')))
    registrar_cambio("Creó Módulo de Servicio", f"Se agregó el servicio técnico: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/productos', methods=['POST'])
@login_required
def guardar_producto():
    d = request.json or {}
    precio = d.get('precio', 0)
    try: precio = float(precio) if precio else 0
    except: precio = 0
    db_query("INSERT INTO productos (nombre, precio, imagen, categoria) VALUES (%s, %s, %s, %s)", (d.get('nombre', ''), precio, d.get('imagen', ''), d.get('categoria', 'Otros')))
    registrar_cambio("Subió Pieza/Equipo", f"Se añadió al catálogo de la tienda: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios/<int:id>', methods=['PUT'])
@login_required
def editar_servicio(id):
    d = request.json or {}
    db_query("UPDATE servicios SET icono=%s, titulo=%s, descripcion=%s, imagen=%s, proceso=%s, beneficios=%s WHERE id=%s", (d.get('icono', '⚙'), d.get('titulo', ''), d.get('descripcion', ''), d.get('imagen',''), d.get('proceso', ''), d.get('beneficios', ''), id))
    registrar_cambio("Actualizó Desglose Técnico", f"Se modificó el servicio ID {id}: {d.get('titulo', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/productos/<int:id>', methods=['PUT'])
@login_required
def editar_producto(id):
    d = request.json or {}
    precio = d.get('precio', 0)
    try: precio = float(precio) if precio else 0
    except: precio = 0
    db_query("UPDATE productos SET nombre=%s, precio=%s, imagen=%s, categoria=%s WHERE id=%s", (d.get('nombre', ''), precio, d.get('imagen',''), d.get('categoria', 'Otros'), id))
    registrar_cambio("Modificó Precio/Pieza", f"Se actualizó el producto ID {id}: {d.get('nombre', '')}")
    return jsonify({"mensaje": "✅"})

@app.route('/api/eliminar/<tabla>/<int:id>', methods=['DELETE'])
@login_required
def eliminar_item(tabla, id):
    tablas_permitidas = ['productos', 'servicios', 'socios', 'resenas', 'beneficios', 'clientes_objetivos', 'empresas_recomiendan', 'clientes_facturacion', 'productos_facturacion']
    if tabla in tablas_permitidas:
        if tabla in ['clientes_facturacion', 'productos_facturacion']:
            id_emp = get_empresa_id_from_session()
            db_query(f"DELETE FROM {tabla} WHERE id = %s AND id_empresa = %s", (id, id_emp))
        else:
            db_query(f"DELETE FROM {tabla} WHERE id = %s", (id,))
        registrar_cambio("Eliminó Contenido", f"Se borró el registro con ID {id} de la tabla '{tabla}'")
        return jsonify({"mensaje": "🗑️"})
    return jsonify({"error": "No válida"}), 400

@app.route('/api/admin/tickets', methods=['GET'])
@login_required
def listar_tickets_admin():
    if not es_admin(): return jsonify({"message": "Acceso denegado"}), 403
    try:
        try:
            query = """
                SELECT t.id, t.empresa_id, e.nombre, t.contacto, t.asunto, 
                       t.descripcion, t.prioridad, t.estado, t.fecha, t.atendido_por 
                FROM tickets_soporte t 
                LEFT JOIN empresas_recomiendan e ON t.empresa_id = e.id 
                ORDER BY t.fecha DESC
            """
            tickets_raw = db_query(query, fetch=True) or []
        except Exception:
            query = """
                SELECT t.id, t.empresa_id, e.nombre, t.contacto, t.asunto, 
                       t.descripcion, t.prioridad, t.estado, t.fecha 
                FROM tickets_soporte t 
                LEFT JOIN empresas_recomiendan e ON t.empresa_id = e.id 
                ORDER BY t.fecha DESC
            """
            tickets_raw = db_query(query, fetch=True) or []
        
        return jsonify([{
            "id": r[0], "empresa_id": r[1], "empresa_nombre": r[2] or "Sin Empresa", 
            "contacto": r[3], "asunto": r[4], "descripcion": r[5], 
            "prioridad": r[6], "estado": r[7], "fecha": str(r[8]),
            "atendido_por": r[9] if len(r) > 9 and r[9] else "Pendiente revisión"
        } for r in tickets_raw])
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/tickets/crear', methods=['POST'])
def crear_ticket():
    d = request.json
    try:
        empresa_id = d.get('empresa_id')
        usuario_id = session.get('usuario_id', None)
        
        if not empresa_id:
            empresa_val = session.get('empresa')
            if not empresa_val:
                return jsonify({"success": False, "message": "No se proporcionó empresa y no hay sesión activa."}), 400
                
            if str(empresa_val).isdigit():
                empresa_id = int(empresa_val)
            else:
                empresa_res = db_query("SELECT id FROM empresas_recomiendan WHERE nombre = %s", (empresa_val,), fetch=True)
                if not empresa_res:
                    db_query("INSERT INTO empresas_recomiendan (nombre) VALUES (%s)", (empresa_val,))
                    empresa_res = db_query("SELECT id FROM empresas_recomiendan WHERE nombre = %s", (empresa_val,), fetch=True)
                empresa_id = empresa_res[0][0]

        usuario_log = session.get('usuario', d.get('contacto', 'Usuario Público'))
        
        try:
            db_query("""INSERT INTO tickets_soporte (empresa_id, usuario_id, contacto, asunto, descripcion, prioridad, whatsapp) VALUES (%s, %s, %s, %s, %s, %s, %s)""", (empresa_id, usuario_id, d.get('contacto'), d.get('asunto'), d.get('descripcion'), d.get('prioridad'), d.get('whatsapp')))
        except Exception:
            db_query("""INSERT INTO tickets_soporte (empresa_id, contacto, asunto, descripcion, prioridad) VALUES (%s, %s, %s, %s, %s)""", (empresa_id, d.get('contacto'), d.get('asunto'), d.get('descripcion'), d.get('prioridad')))
            
        registrar_cambio("Ticket Creado", f"El usuario {usuario_log} creó un ticket de prioridad {d.get('prioridad')}")
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500
    
@app.route('/api/admin/tickets/<int:id>', methods=['DELETE'])
@login_required
def eliminar_ticket_admin(id):
    if not es_admin(): return jsonify({"message": "Denegado"}), 403
    try:
        db_query("DELETE FROM tickets_soporte WHERE id = %s", (id,))
        registrar_cambio("Eliminó Ticket", f"Ticket ID {id} eliminado de forma permanente")
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/tickets/<int:id>/estado', methods=['POST'])
@login_required
def cambiar_estado_ticket(id):
    if not es_admin(): return jsonify({"message": "Denegado"}), 403
    estado = request.json.get('estado')
    admin_nombre = session.get('usuario', 'Soporte Técnico')
    try:
        try:
            db_query("UPDATE tickets_soporte SET estado = %s, atendido_por = %s WHERE id = %s", (estado, admin_nombre, id))
        except Exception:
            db_query("UPDATE tickets_soporte SET estado = %s WHERE id = %s", (estado, id))
            
        registrar_cambio("Actualizó Ticket", f"Ticket ID {id} marcado como {estado}")
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

if __name__ == '__main__':
    initialize_database()
    app.run(debug=True, port=5001)