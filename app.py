from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
import requests
import random
from datetime import datetime
import xml.etree.ElementTree as ET
import base64
import json

app = Flask(__name__)

# Configuración de CORS con soporte estricto para credenciales
CORS(app, supports_credentials=True)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_HTTPONLY=True
)

# Conexión a la base de datos Neon configurada en Vercel
DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON') or os.environ.get('DATABASE_URL')

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
    
    # Tablas de contenido y configuración base
    c.execute('''CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT DEFAULT 'Otros')''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT, proceso TEXT, beneficios TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, rol VARCHAR(20) NOT NULL CHECK (rol IN ('admin', 'personal')), nombre VARCHAR(100) NOT NULL, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial_cambios (id SERIAL PRIMARY KEY, usuario_id INT NULL, usuario_nombre VARCHAR(50) NOT NULL, accion VARCHAR(100) NOT NULL, detalle TEXT NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT NOT NULL, imagen TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS tickets_soporte (id SERIAL PRIMARY KEY, empresa_id INT REFERENCES empresas_recomiendan(id) ON DELETE CASCADE, contacto VARCHAR(100) NOT NULL, whatsapp VARCHAR(50), asunto VARCHAR(200) NOT NULL, descripcion TEXT NOT NULL, prioridad VARCHAR(20) NOT NULL, estado VARCHAR(20) DEFAULT 'Abierto', fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Tablas maestras de facturación e integración Hacienda
    c.execute('''CREATE TABLE IF NOT EXISTS clientes (id_cliente SERIAL PRIMARY KEY, cedula TEXT, nombre_completo TEXT, correo TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS empresa (id_empresa SERIAL PRIMARY KEY, cedula_juridica TEXT, nombre_empresa TEXT, correo TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Facturas (id_factura SERIAL PRIMARY KEY, Id_Empresa INT, Id_Cliente INT, Consecutivo TEXT, Clave_50_Digitos TEXT, Condicion_Venta TEXT, Medio_Pago TEXT, Total_Servicios_Gravados NUMERIC, Total_Impuesto NUMERIC, Total_Comprobante NUMERIC, Estado_Hacienda TEXT, Mensaje_Hacienda TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracionhacienda (id_configuracion SERIAL PRIMARY KEY, id_empresa INT NOT NULL, cedula_juridica VARCHAR(20) DEFAULT '3101000000', hacienda_usuario_idp TEXT NOT NULL, hacienda_password_idp TEXT NOT NULL, ruta_llave_p12 TEXT NOT NULL, pin_llave_p12 VARCHAR(10) NOT NULL, ambiente_produccion BOOLEAN DEFAULT FALSE)''')
    
    conn.commit()
    c.close()
    conn.close()

# Ejecutar una sola vez al cargar la aplicación (Eliminamos el @app.before_request)
init_db()

def registrar_cambio(accion, detalle):
    usuario_id = session.get('user_id')
    usuario_nombre = session.get('nombre', 'Sistema / Web')
    try:
        db_query(
            "INSERT INTO historial_cambios (usuario_id, usuario_nombre, accion, detalle) VALUES (%s, %s, %s, %s)",
            (usuario_id, usuario_nombre, accion, detalle)
        )
    except Exception as e:
        print(f"Error guardando log de auditoría: {e}")

# ==========================================
# 🇨🇷 MÓDULO DE FACTURACIÓN: CONFIGURACIÓN HACIENDA
# ==========================================

@app.route('/api/admin/configuracion-hacienda', methods=['POST'])
def guardar_configuracion_hacienda():
    if not session.get('rol'): return jsonify({"message": "Acceso denegado"}), 403

    usuario_idp = request.form.get('usuario_idp')
    password_idp = request.form.get('password_idp')
    pin_p12 = request.form.get('pin_p12')
    ambiente = request.form.get('ambiente')
    ambiente_produccion = True if ambiente in ['true', 'on', True] else False
    archivo_p12 = request.files.get('archivo_p12')
    id_empresa_actual = request.form.get('id_empresa', 1)

    if not usuario_idp or not password_idp or not pin_p12 or not archivo_p12:
        return jsonify({"success": False, "message": "Todos los campos de Hacienda son requeridos"}), 400

    try:
        contenido_binario = archivo_p12.read()
        p12_base64 = base64.b64encode(contenido_binario).decode('utf-8')

        existe = db_query("SELECT id_configuracion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa_actual,), fetch=True)
        
        if existe:
            db_query("""
                UPDATE configuracionhacienda 
                SET hacienda_usuario_idp = %s, hacienda_password_idp = %s, 
                    ruta_llave_p12 = %s, pin_llave_p12 = %s, ambiente_produccion = %s
                WHERE id_empresa = %s
            """, (usuario_idp, password_idp, p12_base64, pin_p12, ambiente_produccion, id_empresa_actual))
        else:
            db_query("""
                INSERT INTO configuracionhacienda (
                    id_empresa, hacienda_usuario_idp, hacienda_password_idp, 
                    ruta_llave_p12, pin_llave_p12, ambiente_produccion
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (id_empresa_actual, usuario_idp, password_idp, p12_base64, pin_p12, ambiente_produccion))

        registrar_cambio("Configuró Hacienda", f"Credenciales actualizadas para Empresa ID: {id_empresa_actual}")
        return jsonify({"success": True, "message": "Configuración de Hacienda guardada correctamente en Neon"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error en procesamiento interno: {str(e)}"}), 500

@app.route('/api/admin/configuracion-hacienda/verificar', methods=['GET'])
def verificar_configuracion_hacienda():
    if not session.get('rol'): return jsonify({"message": "Acceso denegado"}), 403
    id_empresa = request.args.get('id_empresa', 1)
    res = db_query("SELECT hacienda_usuario_idp, ambiente_produccion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    if res:
        return jsonify({"configurado": True, "usuario_idp": res[0][0], "ambiente": "Producción" if res[0][1] else "Pruebas / Sandbox"})
    return jsonify({"configurado": False})

# ==========================================
# 🔐 MOTOR DE AUTENTICACIÓN OAUTH 2.0 CON HACIENDA
# ==========================================

def obtener_oauth_token_hacienda(id_empresa):
    res = db_query("SELECT hacienda_usuario_idp, hacienda_password_idp, ambiente_produccion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    if not res: raise Exception(f"La empresa con ID {id_empresa} no tiene configuradas sus credenciales.")
    
    usuario_idp, password_idp, ambiente_produccion = res[0]
    url_auth = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token" if ambiente_produccion else "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token"

    payload = {'grant_type': 'password', 'client_id': 'api-prod' if ambiente_produccion else 'api-stag', 'username': usuario_idp, 'password': password_idp}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    try:
        response = requests.post(url_auth, data=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            datos_token = response.json()
            return {"success": True, "access_token": datos_token.get("access_token")}
        else:
            return {"success": False, "error_detalle": response.text}
    except Exception as e:
        return {"success": False, "error_detalle": str(e)}

# ==========================================
# 📐 GENERACIÓN DE XML Y ENVÍO A HACIENDA
# ==========================================

def calcular_clave_50_digitos(cedula_emisor, consecutivo, situacion="1"):
    ahora = datetime.now()
    dia, mes, ano = ahora.strftime("%d"), ahora.strftime("%m"), ahora.strftime("%y")
    cedula_12 = "".join(filter(str.isdigit, str(cedula_emisor))).zfill(12)
    codigo_seguridad = "".join([str(random.randint(0, 9)) for _ in range(8)])
    return f"506{dia}{mes}{ano}{cedula_12}{consecutivo}{situacion}{codigo_seguridad}"

def generar_xml_factura_44(datos_factura, lineas_detalle):
    NS_FACTURA = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturelectronica"
    root = ET.Element("FacturaElectronica", {"xmlns": NS_FACTURA, "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"})

    ET.SubElement(root, "Clave").text = datos_factura['clave']
    ET.SubElement(root, "CodigoActividad").text = "620201"
    ET.SubElement(root, "NumeroConsecutivo").text = datos_factura['consecutivo']
    ET.SubElement(root, "FechaEmision").text = datetime.now().isoformat()[:-3] + "-06:00"
    
    emisor = ET.SubElement(root, "Emisor")
    ET.SubElement(emisor, "Nombre").text = datos_factura['emisor_nombre']
    id_emisor = ET.SubElement(emisor, "Identificacion")
    ET.SubElement(id_emisor, "Tipo").text = "02"
    ET.SubElement(id_emisor, "Numero").text = datos_factura['emisor_cedula']
    ET.SubElement(emisor, "CorreoElectronico").text = datos_factura.get('emisor_correo', 'soporte@icartech.cr')

    receptor = ET.SubElement(root, "Receptor")
    ET.SubElement(receptor, "Nombre").text = datos_factura['cliente_nombre']
    id_receptor = ET.SubElement(receptor, "Identificacion")
    ET.SubElement(id_receptor, "Tipo").text = "01"
    ET.SubElement(id_receptor, "Numero").text = datos_factura['cliente_cedula']

    ET.SubElement(root, "CondicionVenta").text = datos_factura.get('condicion_venta', '01')
    ET.SubElement(root, "MedioPago").text = datos_factura.get('medio_pago', '04')

    detalle_nodo = ET.SubElement(root, "DetalleServicio")
    total_serv = 0.0
    total_iva = 0.0

    for idx, linea in enumerate(lineas_detalle, start=1):
        linea_nodo = ET.SubElement(detalle_nodo, "LineaDetalle")
        ET.SubElement(linea_nodo, "NumeroLinea").text = str(idx)
        ET.SubElement(linea_nodo, "Codigo").text = linea['codigo_cabys']
        ET.SubElement(linea_nodo, "Cantidad").text = f"{float(linea['cantidad']):.3f}"
        ET.SubElement(linea_nodo, "UnidadMedida").text = "Sp"
        ET.SubElement(linea_nodo, "Detalle").text = linea['descripcion']
        ET.SubElement(linea_nodo, "PrecioUnitario").text = f"{float(linea['precio_unitario']):.5f}"
        ET.SubElement(linea_nodo, "MontoTotal").text = f"{float(linea['monto_total']):.5f}"
        ET.SubElement(linea_nodo, "SubTotal").text = f"{float(linea['monto_total']):.5f}"

        monto_impuesto = float(linea['monto_total']) * 0.13
        total_serv += float(linea['monto_total'])
        total_iva += monto_impuesto

        impuesto_nodo = ET.SubElement(linea_nodo, "Impuesto")
        ET.SubElement(impuesto_nodo, "Codigo").text = "01"
        ET.SubElement(impuesto_nodo, "CodigoTarifa").text = "08"
        ET.SubElement(impuesto_nodo, "Tarifa").text = "13.00"
        ET.SubElement(impuesto_nodo, "Monto").text = f"{monto_impuesto:.5f}"
        ET.SubElement(linea_nodo, "MontoTotalLinea").text = f"{(float(linea['monto_total']) + monto_impuesto):.5f}"

    resumen = ET.SubElement(root, "ResumenFactura")
    ET.SubElement(resumen, "CodigoTipoMoneda").text = "CRC"
    ET.SubElement(resumen, "TipoCambio").text = "1.00000"
    ET.SubElement(resumen, "TotalServGravados").text = f"{total_serv:.5f}"
    ET.SubElement(resumen, "TotalGravado").text = f"{total_serv:.5f}"
    ET.SubElement(resumen, "TotalVenta").text = f"{total_serv:.5f}"
    ET.SubElement(resumen, "TotalVentaNeto").text = f"{total_serv:.5f}"
    ET.SubElement(resumen, "TotalImpuesto").text = f"{total_iva:.5f}"
    ET.SubElement(resumen, "TotalComprobante").text = f"{(total_serv + total_iva):.5f}"

    return ET.tostring(root, encoding="utf-8").decode("utf-8")

def enviar_factura_hacienda(id_empresa, datos_factura, xml_string):
    token_data = obtener_oauth_token_hacienda(id_empresa)
    if not token_data["success"]: return token_data
    
    token = token_data["access_token"]
    res_empresa = db_query("SELECT ambiente_produccion, cedula_juridica FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    ambiente_produccion, cedula_emisor = res_empresa[0]

    url_recepcion = "https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion" if ambiente_produccion else "https://api-sandbox.comprobanteselectronicos.go.cr/recepcion/v1/recepcion"
    xml_base64 = base64.b64encode(xml_string.encode('utf-8')).decode('utf-8')

    payload = {
        "clave": datos_factura["clave"],
        "fecha": datetime.now().isoformat()[:-3] + "-06:00",
        "emisor": {"tipoIdentificacion": "02", "numeroIdentificacion": cedula_emisor},
        "receptor": {"tipoIdentificacion": "01", "numeroIdentificacion": datos_factura["cliente_cedula"]},
        "comprobanteXml": xml_base64
    }

    try:
        response = requests.post(url_recepcion, json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=10)
        if response.status_code in [202, 200]:
            return {"success": True, "message": "Factura recibida por Hacienda."}
        return {"success": False, "message": f"Rechazado ({response.status_code}): {response.text}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.route('/api/facturacion/emitir', methods=['POST'])
def emitir_factura_electronica_api():
    d = request.json or {}
    cliente_id = d.get('cliente_id')
    lineas_frontend = d.get('lineas', [])
    id_empresa_actual = 1 

    if not cliente_id or not lineas_frontend: return jsonify({"success": False, "message": "Faltan datos."}), 400

    try:
        res_emisor = db_query("SELECT cedula_juridica, nombre_empresa, correo FROM empresa WHERE id_empresa = %s", (id_empresa_actual,), fetch=True)
        res_cliente = db_query("SELECT cedula, nombre_completo, correo FROM clientes WHERE id_cliente = %s", (cliente_id,), fetch=True)
        
        if not res_emisor or not res_cliente: return jsonify({"success": False, "message": "Empresa o cliente no válido."}), 400

        emisor_datos = {"cedula": res_emisor[0][0], "nombre": res_emisor[0][1], "correo": res_emisor[0][2]}
        cliente_datos = {"cedula": res_cliente[0][0], "nombre": res_cliente[0][1], "correo": res_cliente[0][2]}

        consecutivo_sistema = "0010000101" + datetime.now().strftime("%H%M%S").zfill(10)
        clave_50 = calcular_clave_50_digitos(emisor_datos["cedula"], consecutivo_sistema)

        total_serv_gravados = sum(float(l['monto_total']) for l in lineas_frontend)
        total_iva = total_serv_gravados * 0.13

        db_query("""
            INSERT INTO Facturas (Id_Empresa, Id_Cliente, Consecutivo, Clave_50_Digitos, Condicion_Venta, Medio_Pago, Total_Servicios_Gravados, Total_Impuesto, Total_Comprobante, Estado_Hacienda) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendiente')
        """, (id_empresa_actual, cliente_id, consecutivo_sistema, clave_50, d.get('condicion_venta', '01'), d.get('medio_pago', '04'), total_serv_gravados, total_iva, total_serv_gravados + total_iva))

        datos_xml_maestro = {
            'clave': clave_50, 'consecutivo': consecutivo_sistema,
            'emisor_nombre': emisor_datos["nombre"], 'emisor_cedula': emisor_datos["cedula"], 'emisor_correo': emisor_datos["correo"],
            'cliente_nombre': cliente_datos["nombre"], 'cliente_cedula': cliente_datos["cedula"],
            'condicion_venta': d.get('condicion_venta', '01'), 'medio_pago': d.get('medio_pago', '04')
        }

        xml_generado = generar_xml_factura_44(datos_xml_maestro, lineas_frontend)
        resultado_envio = enviar_factura_hacienda(id_empresa_actual, datos_xml_maestro, xml_generado)

        if resultado_envio["success"]:
            return jsonify({"success": True, "clave": clave_50, "consecutivo": consecutivo_sistema})
        else:
            db_query("UPDATE Facturas SET Estado_Hacienda = 'Rechazado', Mensaje_Hacienda = %s WHERE Clave_50_Digitos = %s", (resultado_envio["message"], clave_50))
            return jsonify({"success": False, "message": resultado_envio["message"]}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==========================================
# 🔐 RUTAS DE AUTENTICACIÓN Y ADMINISTRACIÓN
# ==========================================

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    res = db_query("SELECT id, usuario, password_hash, rol, nombre FROM usuarios WHERE usuario = %s", (d.get('usuario'),), fetch=True)
    if res and check_password_hash(res[0][2], d.get('password')):
        session.update({'user_id': res[0][0], 'rol': res[0][3], 'nombre': res[0][4]})
        return jsonify({"success": True, "usuario": res[0][1], "rol": res[0][3]})
    return jsonify({"success": False}), 401

@app.route('/api/admin/logs', methods=['GET'])
def obtener_logs():
    if session.get('rol') != 'admin': return jsonify([]), 403
    logs = db_query("SELECT fecha, usuario_nombre, accion, detalle FROM historial_cambios ORDER BY fecha DESC", fetch=True) or []
    return jsonify([{"fecha": str(r[0]), "usuario": r[1], "accion": r[2], "detalle": r[3]} for r in logs])

@app.route('/api/admin/usuarios', methods=['GET'])
def listar_usuarios():
    if session.get('rol') != 'admin': return jsonify([]), 403
    users = db_query("SELECT id, usuario, rol, nombre FROM usuarios ORDER BY id ASC", fetch=True) or []
    return jsonify([{"id": r[0], "usuario": r[1], "rol": r[2], "nombre": r[3]} for r in users])

@app.route('/api/admin/crear-usuario', methods=['POST'])
def crear_usuario():
    if session.get('rol') != 'admin': return jsonify({"success": False}), 403
    d = request.json
    try:
        db_query("INSERT INTO usuarios (usuario, password_hash, rol, nombre) VALUES (%s, %s, 'personal', %s)", (d['usuario'], generate_password_hash(d['password']), d['nombre']))
        registrar_cambio("Creó Usuario", f"Registró a: {d['nombre']}")
        return jsonify({"success": True})
    except: return jsonify({"success": False}), 400

@app.route('/api/admin/eliminar-usuario/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    if session.get('rol') != 'admin': return jsonify({"success": False}), 403
    db_query("DELETE FROM usuarios WHERE id = %s", (id,))
    return jsonify({"success": True})

# ==========================================
# 🎫 RUTAS DE TICKETS Y SOPORTE
# ==========================================

@app.route('/api/tickets', methods=['POST'])
def crear_ticket_publico():
    d = request.json or {}
    db_query("INSERT INTO tickets_soporte (empresa_id, contacto, whatsapp, asunto, descripcion, prioridad) VALUES (%s, %s, %s, %s, %s, %s)",
             (d.get('empresa_id'), d.get('contacto'), d.get('whatsapp'), d.get('asunto'), d.get('descripcion'), d.get('prioridad', 'Alta')))
    registrar_cambio("Ticket Creado", f"Reportado por {d.get('contacto')}")
    return jsonify({"success": True})

@app.route('/api/admin/tickets', methods=['GET'])
def listar_tickets_admin():
    if not session.get('rol'): return jsonify([]), 401
    tickets = db_query('''SELECT t.id, t.empresa_id, e.nombre, t.contacto, t.asunto, t.descripcion, t.prioridad, t.estado, t.fecha 
                          FROM tickets_soporte t LEFT JOIN empresas_recomiendan e ON t.empresa_id = e.id ORDER BY t.fecha DESC''', fetch=True) or []
    return jsonify([{"id": r[0], "empresa_nombre": r[2], "contacto": r[3], "asunto": r[4], "descripcion": r[5], "prioridad": r[6], "estado": r[7], "fecha": str(r[8])} for r in tickets])

@app.route('/api/admin/tickets/<int:id>/estado', methods=['POST'])
def cambiar_estado_ticket(id):
    if not session.get('rol'): return jsonify({"success": False}), 401
    db_query("UPDATE tickets_soporte SET estado = %s WHERE id = %s", (request.json.get('estado', 'Resuelto'), id))
    return jsonify({"success": True})

# ==========================================
# 🛠️ RUTAS DE CONTENIDO GENERAL
# ==========================================

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    config = {r[0]: r[1] for r in (db_query("SELECT clave, valor FROM configuracion", fetch=True) or [])}
    servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4]} for r in (db_query("SELECT id, icono, titulo, descripcion, imagen FROM servicios", fetch=True) or [])]
    prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]), "imagen": r[3], "categoria": r[4]} for r in (db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or [])]
    return jsonify({"config": config, "servicios": servs, "productos": prods})

@app.route('/api/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar_item(tabla, id):
    if tabla in ['productos', 'servicios', 'empresas_recomiendan']:
        db_query(f"DELETE FROM {tabla} WHERE id = %s", (id,))
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

if __name__ == '__main__':
    app.run(debug=True)