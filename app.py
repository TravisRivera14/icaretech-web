from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
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

app = Flask(__name__)
CORS(app, supports_credentials=True)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')

app.config.update(
    SESSION_COOKIE_SECURE=True, 
    SESSION_COOKIE_SAMESITE='none', 
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
    
    # Nuevas tablas de permisos (Centro de Operaciones)
    c.execute('''CREATE TABLE IF NOT EXISTS permisos_empresa (empresa_id INT PRIMARY KEY, facturacion BOOLEAN DEFAULT FALSE, datacenter BOOLEAN DEFAULT FALSE, inventario BOOLEAN DEFAULT FALSE, tickets BOOLEAN DEFAULT TRUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS permisos_usuario (usuario_id INT PRIMARY KEY, facturacion BOOLEAN DEFAULT FALSE, datacenter BOOLEAN DEFAULT FALSE, inventario BOOLEAN DEFAULT FALSE, tickets BOOLEAN DEFAULT TRUE)''')
    
    # Asegurar columnas (migración silenciosa)
    try: c.execute('''ALTER TABLE usuarios ADD COLUMN correo VARCHAR(150)''')
    except: conn.rollback()
    try: c.execute('''ALTER TABLE usuarios ADD COLUMN telefono VARCHAR(20)''')
    except: conn.rollback()
    try: c.execute('''ALTER TABLE tickets_soporte ADD COLUMN usuario_id INT''')
    except: conn.rollback()

    conn.commit(); c.close(); conn.close()

def registrar_cambio(accion, detalle):
    usuario_id = session.get('usuario_id')
    usuario_nombre = session.get('usuario', 'Sistema / Web')
    try: db_query("INSERT INTO historial_cambios (usuario_id, usuario_nombre, accion, detalle) VALUES (%s, %s, %s, %s)", (usuario_id, usuario_nombre, accion, detalle))
    except Exception as e: print(f"Error log: {e}")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session: return jsonify({"error": "No autorizado"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    usr = data.get('usuario', '').strip()
    pwd = data.get('password', '').strip()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, password_hash, rol, debe_cambiar_pass, empresa FROM usuarios WHERE LOWER(usuario) = LOWER(%s) OR LOWER(correo) = LOWER(%s) OR telefono = %s", (usr, usr, usr))
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

@app.route('/api/cliente/datos-operativos', methods=['GET'])
@login_required
def obtener_datos_operativos():
    empresa_val = session.get('empresa')
    rol = session.get('rol')
    usuario_id = session.get('usuario_id')
    if not empresa_val: return jsonify({"error": "No asociado a empresa"}), 403
    
    try:
        if str(empresa_val).isdigit(): id_empresa = int(empresa_val)
        else:
            res_emp = db_query("SELECT id FROM empresas_recomiendan WHERE nombre = %s", (empresa_val,), fetch=True)
            if not res_emp: return jsonify({"error": "Empresa no registrada"}), 404
            id_empresa = res_emp[0][0]
            
        # Determinar Permisos Modulares Finales
        perm_emp = db_query("SELECT facturacion, datacenter, inventario, tickets FROM permisos_empresa WHERE empresa_id = %s", (id_empresa,), fetch=True)
        perm_usr = db_query("SELECT facturacion, datacenter, inventario, tickets FROM permisos_usuario WHERE usuario_id = %s", (usuario_id,), fetch=True)
        
        permisos_finales = {"facturacion": False, "datacenter": False, "inventario": False, "tickets": True}
        if perm_emp and perm_usr:
            e_f, e_d, e_i, e_t = perm_emp[0]
            u_f, u_d, u_i, u_t = perm_usr[0]
            permisos_finales = {
                "facturacion": e_f and u_f,
                "datacenter": e_d and u_d,
                "inventario": e_i and u_i,
                "tickets": e_t and u_t
            }

        facturas = []
        if permisos_finales["facturacion"]:
            facturas = db_query("SELECT id, consecutivo, fecha, total_comprobante, estado_hacienda FROM Facturas WHERE id_empresa = %s", (id_empresa,), fetch=True) or []
            
        # Lógica de Roles para Tickets
        if rol == 'cliente_admin':
            tickets = db_query("SELECT id, asunto, estado, prioridad, fecha FROM tickets_soporte WHERE empresa_id = %s ORDER BY fecha DESC", (id_empresa,), fetch=True) or []
        else:
            tickets = db_query("SELECT id, asunto, estado, prioridad, fecha FROM tickets_soporte WHERE usuario_id = %s ORDER BY fecha DESC", (usuario_id,), fetch=True) or []
            
        return jsonify({
            "facturas": [{"id": f[0], "consecutivo": f[1], "fecha": str(f[2]), "monto": str(f[3]), "estado": f[4]} for f in facturas],
            "tickets": [{"id": t[0], "asunto": t[1], "estado": t[2], "prioridad": t[3], "fecha": str(t[4])} for t in tickets],
            "permisos": permisos_finales,
            "rol": rol
        })
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/usuarios', methods=['GET'])
@login_required
def listar_usuarios():
    if session.get('rol') not in ['admin', 'personal', 'personal_admin']: return jsonify({"message": "Denegado"}), 403
    users_raw = db_query("SELECT id, usuario, rol, nombre, empresa, correo, telefono FROM usuarios ORDER BY id ASC", fetch=True) or []
    return jsonify([{"id": r[0], "usuario": r[1], "rol": r[2], "nombre": r[3], "empresa_id": r[4], "correo": r[5], "telefono": r[6]} for r in users_raw])

@app.route('/api/admin/crear-usuario', methods=['POST'])
@login_required
def crear_usuario():
    if session.get('rol') not in ['admin', 'personal_admin']: return jsonify({"message": "Acceso denegado"}), 403
    d = request.json or {}
    password_encriptada = generate_password_hash(d.get('password', '12345'))
    try:
        db_query("""INSERT INTO usuarios (nombre, usuario, password_hash, rol, empresa, correo, telefono) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (d.get('nombre'), d.get('usuario'), password_encriptada, d.get('rol'), d.get('empresa_id'), d.get('email'), d.get('telefono')))
        
        # Recuperar ID para asignarle permisos base
        res = db_query("SELECT id FROM usuarios WHERE usuario = %s", (d.get('usuario'),), fetch=True)
        if res:
            db_query("INSERT INTO permisos_usuario (usuario_id, facturacion, datacenter, inventario, tickets) VALUES (%s, true, true, true, true)", (res[0][0],))
            
        registrar_cambio("Creó Usuario", f"Se registró a: {d.get('nombre')} ({d.get('rol')})")
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/admin/editar-usuario', methods=['POST'])
@login_required
def editar_usuario():
    if session.get('rol') not in ['admin', 'personal_admin']: return jsonify({"message": "Acceso denegado"}), 403
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
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/admin/eliminar-usuario/<int:id>', methods=['DELETE'])
@login_required
def eliminar_usuario(id):
    if session.get('rol') not in ['admin', 'personal_admin']: return jsonify({"message": "denegado"}), 403
    db_query("DELETE FROM usuarios WHERE id = %s", (id,))
    db_query("DELETE FROM permisos_usuario WHERE usuario_id = %s", (id,))
    registrar_cambio("Eliminó Usuario", f"ID {id}")
    return jsonify({"success": True})

# ----------------- RUTAS DEL CENTRO DE OPERACIONES (PERMISOS) -----------------
@app.route('/api/admin/operaciones/empresa/<int:empresa_id>', methods=['GET'])
@login_required
def get_permisos_empresa(empresa_id):
    if session.get('rol') not in ['admin', 'personal_admin']: return jsonify({"error": "Denegado"}), 403
    p = db_query("SELECT facturacion, datacenter, inventario, tickets FROM permisos_empresa WHERE empresa_id = %s", (empresa_id,), fetch=True)
    if p: return jsonify({"facturacion": p[0][0], "datacenter": p[0][1], "inventario": p[0][2], "tickets": p[0][3]})
    # Si no existe, crear registro base
    db_query("INSERT INTO permisos_empresa (empresa_id, facturacion, datacenter, inventario, tickets) VALUES (%s, false, false, false, true)", (empresa_id,))
    return jsonify({"facturacion": False, "datacenter": False, "inventario": False, "tickets": True})

@app.route('/api/admin/operaciones/empresa', methods=['POST'])
@login_required
def save_permisos_empresa():
    if session.get('rol') not in ['admin', 'personal_admin']: return jsonify({"error": "Denegado"}), 403
    d = request.json
    db_query("UPDATE permisos_empresa SET facturacion=%s, datacenter=%s, inventario=%s, tickets=%s WHERE empresa_id=%s",
             (d.get('facturacion'), d.get('datacenter'), d.get('inventario'), d.get('tickets'), d.get('empresa_id')))
    return jsonify({"success": True})

@app.route('/api/admin/operaciones/usuarios/<int:empresa_id>', methods=['GET'])
@login_required
def get_permisos_usuarios_empresa(empresa_id):
    if session.get('rol') not in ['admin', 'personal_admin']: return jsonify({"error": "Denegado"}), 403
    users = db_query("SELECT id, nombre, rol FROM usuarios WHERE empresa = %s", (str(empresa_id),), fetch=True) or []
    lista = []
    for u in users:
        u_id = u[0]
        p = db_query("SELECT facturacion, datacenter, inventario, tickets FROM permisos_usuario WHERE usuario_id = %s", (u_id,), fetch=True)
        if not p:
            db_query("INSERT INTO permisos_usuario (usuario_id, facturacion, datacenter, inventario, tickets) VALUES (%s, true, true, true, true)", (u_id,))
            p = [(True, True, True, True)]
        lista.append({"id": u_id, "nombre": u[1], "rol": u[2], "permisos": {"facturacion": p[0][0], "datacenter": p[0][1], "inventario": p[0][2], "tickets": p[0][3]}})
    return jsonify(lista)

@app.route('/api/admin/operaciones/usuario', methods=['POST'])
@login_required
def save_permisos_usuario():
    if session.get('rol') not in ['admin', 'personal_admin']: return jsonify({"error": "Denegado"}), 403
    d = request.json
    db_query("UPDATE permisos_usuario SET facturacion=%s, datacenter=%s, inventario=%s, tickets=%s WHERE usuario_id=%s",
             (d.get('facturacion'), d.get('datacenter'), d.get('inventario'), d.get('tickets'), d.get('usuario_id')))
    return jsonify({"success": True})
# ------------------------------------------------------------------------------

@app.route('/api/tickets/crear', methods=['POST'])
def crear_ticket():
    d = request.json
    try:
        empresa_id = d.get('empresa_id')
        usuario_id = session.get('usuario_id', None)
        
        if not empresa_id:
            empresa_val = session.get('empresa')
            if not empresa_val: return jsonify({"success": False, "message": "No hay sesión o empresa."}), 400
            if str(empresa_val).isdigit(): empresa_id = int(empresa_val)
            else:
                emp_r = db_query("SELECT id FROM empresas_recomiendan WHERE nombre = %s", (empresa_val,), fetch=True)
                empresa_id = emp_r[0][0] if emp_r else None

        db_query("""INSERT INTO tickets_soporte (empresa_id, usuario_id, contacto, asunto, descripcion, prioridad, whatsapp) VALUES (%s, %s, %s, %s, %s, %s, %s)""", 
                 (empresa_id, usuario_id, d.get('contacto'), d.get('asunto'), d.get('descripcion'), d.get('prioridad'), d.get('whatsapp')))
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/tickets', methods=['GET'])
@login_required
def listar_tickets_admin():
    if session.get('rol') not in ['admin', 'personal', 'personal_admin']: return jsonify({"message": "Denegado"}), 403
    try:
        query = """SELECT t.id, t.empresa_id, e.nombre, t.contacto, t.asunto, t.descripcion, t.prioridad, t.estado, t.fecha 
                   FROM tickets_soporte t LEFT JOIN empresas_recomiendan e ON t.empresa_id = e.id ORDER BY t.fecha DESC"""
        res = db_query(query, fetch=True) or []
        return jsonify([{"id": r[0], "empresa_id": r[1], "empresa_nombre": r[2] or "N/A", "contacto": r[3], "asunto": r[4], "descripcion": r[5], "prioridad": r[6], "estado": r[7], "fecha": r[8]} for r in res])
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}
        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        servs = [{"id": r[0], "titulo": r[2]} for r in servs_raw]
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        prods = [{"id": r[0], "nombre": r[1]} for r in prods_raw]
        emp_raw = db_query("SELECT id, nombre, imagen FROM empresas_recomiendan ORDER BY id ASC", fetch=True) or []
        empresas = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in emp_raw]

        return jsonify({"config": config, "servicios": servs, "productos": prods, "empresas": empresas})
    except Exception as e: return jsonify({"error": "Error interno", "detalles": str(e)}), 500

@app.route('/api/recomiendan', methods=['GET'])
def get_empresas():
    emp_raw = db_query("SELECT id, nombre, imagen FROM empresas_recomiendan ORDER BY id ASC", fetch=True) or []
    return jsonify([{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in emp_raw])

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)