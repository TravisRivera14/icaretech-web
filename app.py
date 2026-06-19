from flask import Flask, request, jsonify, send_from_directory, session
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

# Intenta leer la variable de entorno de Vercel, si no, usa el pooler directo de tu Neon
DATABASE_URL = os.environ.get(
    'DATABASE_URL', 
    'postgresql://neondb_owner:npg_rXcGY7BdMpS9@ep-green-forest-ap6dfhlf-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require'
)

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
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, rol VARCHAR(20) NOT NULL CHECK (rol IN ('admin', 'personal')), nombre VARCHAR(100) NOT NULL, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # CORREGIDO: Sintaxis limpia sin el residuo de comillas al final
    c.execute('''CREATE TABLE IF NOT EXISTS historial_cambios (id SERIAL PRIMARY KEY, usuario_id INT NULL, usuario_nombre VARCHAR(50) NOT NULL, accion VARCHAR(100) NOT NULL, detalle TEXT NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT NOT NULL, imagen TEXT DEFAULT '')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS tickets_soporte (
                    id SERIAL PRIMARY KEY, 
                    empresa_id INT REFERENCES empresas_recomiendan(id) ON DELETE CASCADE, 
                    contacto VARCHAR(100) NOT NULL, 
                    whatsapp VARCHAR(50),
                    asunto VARCHAR(200) NOT NULL, 
                    descripcion TEXT NOT NULL, 
                    prioridad VARCHAR(20) NOT NULL, 
                    estado VARCHAR(20) DEFAULT 'Abierto', 
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # INTEGRADO: Tabla maestra de Hacienda enlazada a Neon
    c.execute('''CREATE TABLE IF NOT EXISTS configuracionhacienda (
                    id_configuracion SERIAL PRIMARY KEY,
                    id_empresa INT NOT NULL,
                    cedula_juridica VARCHAR(20) DEFAULT '3101000000',
                    hacienda_usuario_idp TEXT NOT NULL,
                    hacienda_password_idp TEXT NOT NULL,
                    ruta_llave_p12 TEXT NOT NULL,
                    pin_llave_p12 VARCHAR(10) NOT NULL,
                    ambiente_produccion BOOLEAN DEFAULT FALSE)''')
    conn.commit()
    c.close()
    conn.close()

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
    if not session.get('rol'):
        return jsonify({"message": "Acceso denegado"}), 403

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
    if not session.get('rol'):
        return jsonify({"message": "Acceso denegado"}), 403
        
    id_empresa = request.args.get('id_empresa', 1)
    res = db_query("SELECT hacienda_usuario_idp, ambiente_produccion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    
    if res:
        return jsonify({
            "configurado": True,
            "usuario_idp": res[0][0],
            "ambiente": "Producción" if res[0][1] else "Pruebas / Sandbox"
        })
    return jsonify({"configurado": False})


# ==========================================
# ENDPOINT TEMPORAL DE DIAGNÓSTICO (Bypass de Sesión)
# ==========================================
@app.route('/api/admin/facturacion/probar-conexion/1', methods=['GET'])
def probar_conexion_hacienda_test():
    try:
        resultado = obtener_oauth_token_hacienda(1)
        if resultado["success"]:
            return jsonify({
                "status": "Conexión Exitosa",
                "mensaje": "Autenticado correctamente con Hacienda.",
                "token": resultado["access_token"][:15] + "..."
            })
        else:
            return jsonify({
                "status": "Error de Autenticación",
                "mensaje": "Hacienda rechazó las credenciales o la tabla está vacía.",
                "detalles_tecnicos": resultado
            }), 400
    except Exception as e:
        return jsonify({"status": "Error Interno", "error": str(e)}), 500


# ==========================================
# 🔐 FASE 3: MOTOR DE AUTENTICACIÓN OAUTH 2.0 CON HACIENDA
# ==========================================

def obtener_oauth_token_hacienda(id_empresa):
    res = db_query("""
        SELECT hacienda_usuario_idp, hacienda_password_idp, ambiente_produccion 
        FROM configuracionhacienda WHERE id_empresa = %s
    """, (id_empresa,), fetch=True)
    
    if not res:
        raise Exception(f"La empresa con ID {id_empresa} no tiene configuradas sus credenciales de Hacienda.")
    
    usuario_idp = res[0][0]
    password_idp = res[0][1]
    ambiente_produccion = res[0][2]

    if ambiente_produccion:
        url_auth = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token"
    else:
        url_auth = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token"

    payload = {
        'grant_type': 'password',
        'client_id': 'api-stag' if not ambiente_produccion else 'api-prod',
        'username': usuario_idp,
        'password': password_idp
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        response = requests.post(url_auth, data=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            datos_token = response.json()
            return {
                "success": True,
                "access_token": datos_token.get("access_token"),
                "expires_in": datos_token.get("expires_in"),
                "refresh_token": datos_token.get("refresh_token")
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "error_detalle": response.text
            }
    except Exception as e:
        return {
            "success": False,
            "error_detalle": f"No se pudo conectar con el servidor de autenticación de Hacienda: {str(e)}"
        }


# ==========================================
# 📐 FASE 4: GENERACIÓN DE CLAVE DE 50 DÍGITOS Y XML (VERSIÓN 4.4)
# ==========================================

def calcular_clave_50_digitos(cedula_emisor, consecutivo, situacion="1"):
    ahora = datetime.now()
    dia = ahora.strftime("%d")
    mes = ahora.strftime("%m")
    ano = ahora.strftime("%y")

    cedula_limpia = "".join(filter(str.isdigit, str(cedula_emisor)))
    cedula_12 = cedula_limpia.zfill(12)
    codigo_seguridad = "".join([str(random.randint(0, 9)) for _ in range(8)])

    clave = f"506{dia}{mes}{ano}{cedula_12}{consecutivo}{situacion}{codigo_seguridad}"
    if len(clave) != 50:
        raise Exception(f"Error crítico en el cálculo de la clave. Longitud obtenida: {len(clave)} de 50.")
    return clave


def generar_xml_factura_44(datos_factura, lineas_detalle):
    NS_FACTURA = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturelectronica"
    
    root = ET.Element("FacturaElectronica", {
        "xmlns": NS_FACTURA,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": f"{NS_FACTURA} https://www.hacienda.go.cr/ATV/ComprobanteElectronico/v4.4/facturelectronica.xsd"
    })

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
    total_serv_gravados = 0.0
    total_iva = 0.0

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


# ==========================================
# 🚀 FASE 5: ENVÍO ASÍNCRONO Y RECEPCIÓN DE COMPROBANTES
# ==========================================

def enviar_factura_hacienda(id_empresa, datos_factura, xml_string):
    token_data = obtener_oauth_token_hacienda(id_empresa)
    if not token_data["success"]:
        return {"success": False, "message": "Error de autenticación: " + token_data["error_details"]}
    
    token = token_data["access_token"]
    
    res_empresa = db_query("SELECT ambiente_produccion, cedula_juridica FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    ambiente_produccion = res_empresa[0][0]
    cedula_emisor = res_empresa[0][1]

    if ambiente_produccion:
        url_recepcion = "https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion"
    else:
        url_recepcion = "https://api-sandbox.comprobanteselectronicos.go.cr/recepcion/v1/recepcion"

    xml_bytes = xml_string.encode('utf-8')
    xml_base64 = base64.b64encode(xml_bytes).decode('utf-8')

    payload = {
        "clave": datos_factura["clave"],
        "fecha": datetime.now().isoformat()[:-3] + "-06:00",
        "emisor": {
            "tipoIdentificacion": datos_factura.get("emisor_tipo_cedula", "02"),
            "numeroIdentificacion": cedula_emisor
        },
        "receptor": {
            "tipoIdentificacion": datos_factura.get("cliente_tipo_cedula", "01"),
            "numeroIdentificacion": datos_factura["cliente_cedula"]
        },
        "comprobanteXml": xml_base64
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url_recepcion, data=json.dumps(payload), headers=headers, timeout=10)
        if response.status_code in [202, 200]:
            return {"success": True, "message": "Factura recibida por Hacienda en proceso de validación."}
        else:
            return {"success": False, "message": f"Hacienda rechazó el paquete inicial ({response.status_code}): {response.text}"}
    except Exception as e:
        return {"success": False, "message": f"Error de conexión con el API de Recepción: {str(e)}"}


@app.route('/api/admin/facturacion/consultar-estado/<int:id_empresa>/<string:clave>', methods=['GET'])
def consultar_estado_factura(id_empresa, clave):
    if not session.get('rol'):
        return jsonify({"message": "Acceso denegado"}), 403

    res_empresa = db_query("SELECT ambiente_produccion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    if not res_empresa:
        return jsonify({"error": "Empresa no configurada"}), 400
        
    ambiente_produccion = res_empresa[0][0]
    token_data = obtener_oauth_token_hacienda(id_empresa)
    if not token_data["success"]:
        return jsonify({"error": "No se pudo obtener el token de acceso"}), 500

    if ambiente_produccion:
        url_consulta = f"https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/{clave}"
    else:
        url_consulta = f"https://api-sandbox.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/{clave}"

    headers = {
        "Authorization": f"Bearer {token_data['access_token']}"
    }

    try:
        response = requests.get(url_consulta, headers=headers, timeout=10)
        if response.status_code == 200:
            datos_respuesta = response.json()
            estado_final = datos_respuesta.get("ind-estado", "Pendiente")
            
            db_query(
                "UPDATE Facturas SET Estado_Hacienda = %s, Mensaje_Hacienda = %s WHERE Clave_50_Digitos = %s",
                (estado_final.capitalize(), datos_respuesta.get("respuesta-xml", "Procesado"), clave)
            )
            return jsonify({
                "clave": clave,
                "estado_hacienda": estado_final,
                "detalles": "El documento fue procesado con éxito."
            })
        else:
            return jsonify({"status": "Procesando", "message": "Hacienda aún está analizando el documento."}), 202
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# ⚡ RUTA MAESTRA: EMISIÓN COMPLETA DE FACTURA
# ==========================================

@app.route('/api/facturacion/emitir', methods=['POST'])
def emitir_factura_electronica_api():
    # Eliminada protección estricta para pruebas de desarrollo ágil
    d = request.json or {}
    cliente_id = d.get('cliente_id')
    condicion_venta = d.get('condicion_venta', '01')
    medio_pago = d.get('medio_pago', '04')
    lineas_frontend = d.get('lineas', [])
    id_empresa_actual = 1 

    if not cliente_id or not lineas_frontend:
        return jsonify({"success": False, "message": "Faltan datos esenciales (Cliente o Líneas de detalle)"}), 400

    try:
        res_emisor = db_query("SELECT cedula_juridica, nombre_empresa, correo FROM empresa WHERE id_empresa = %s", (id_empresa_actual,), fetch=True)
        if not res_emisor:
            return jsonify({"success": False, "message": "Empresa emisora no registrada o incompleta."}), 400
        
        res_cliente = db_query("SELECT cedula, nombre_completo, correo FROM clientes WHERE id_cliente = %s", (cliente_id,), fetch=True)
        if not res_cliente:
            return jsonify({"success": False, "message": "El cliente seleccionado no existe."}), 400

        emisor_datos = {"cedula": res_emisor[0][0], "nombre": res_emisor[0][1], "correo": res_emisor[0][2]}
        cliente_datos = {"cedula": res_cliente[0][0], "nombre": res_cliente[0][1], "correo": res_cliente[0][2]}

        consecutivo_sistema = "0010000101" + datetime.now().strftime("%H%M%S").zfill(10)
        clave_50 = calcular_clave_50_digitos(emisor_datos["cedula"], consecutivo_sistema)

        total_serv_gravados = sum(float(l['monto_total']) for l in lineas_frontend)
        total_iva = total_serv_gravados * 0.13
        total_comprobante = total_serv_gravados + total_iva

        db_query("""
            INSERT INTO Facturas (
                Id_Empresa, Id_Cliente, Consecutivo, Clave_50_Digitos, 
                Condicion_Venta, Medio_Pago, Total_Servicios_Gravados, Total_Impuesto, Total_Comprobante, Estado_Hacienda
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendiente')
        """, (id_empresa_actual, cliente_id, consecutivo_sistema, clave_50, condicion_venta, medio_pago, total_serv_gravados, total_iva, total_comprobante))

        datos_xml_maestro = {
            'clave': clave_50,
            'consecutivo': consecutivo_sistema,
            'emisor_nombre': emisor_datos["nombre"],
            'emisor_cedula': emisor_datos["cedula"],
            'emisor_correo': emisor_datos["correo"],
            'cliente_nombre': cliente_datos["nombre"],
            'cliente_cedula': cliente_datos["cedula"],
            'cliente_correo': cliente_datos["correo"],
            'condicion_venta': condicion_venta,
            'medio_pago': medio_pago
        }

        xml_generado = generar_xml_factura_44(datos_xml_maestro, lineas_frontend)
        resultado_envio = enviar_factura_hacienda(id_empresa_actual, datos_xml_maestro, xml_generado)

        if resultado_envio["success"]:
            return jsonify({
                "success": True,
                "message": "Factura procesada con éxito",
                "clave": clave_50,
                "consecutivo": consecutivo_sistema
            })
        else:
            db_query("UPDATE Facturas SET Estado_Hacienda = 'Rechazado', Mensaje_Hacienda = %s WHERE Clave_50_Digitos = %s", (resultado_envio["message"], clave_50))
            return jsonify({"success": False, "message": resultado_envio["message"]}), 400
    except Exception as e:
        registrar_cambio("Error Facturación", f"Fallo crítico emitiendo comprobante: {str(e)}")
        return jsonify({"success": False, "message": f"Error interno en el servidor: {str(e)}"}), 500


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


# ==========================================
# 🎫 CONTROLADORES MAESTROS DE SOPORTE Y TICKETS
# ==========================================

@app.route('/api/tickets', methods=['POST'])
def crear_ticket_publico():
    d = request.json or {}
    empresa_id = d.get('empresa_id')
    contacto = d.get('contacto')
    whatsapp = d.get('whatsapp') 
    asunto = d.get('asunto')
    descripcion = d.get('descripcion')
    prioridad = d.get('prioridad', 'Alta')

    if not contacto or not asunto or not descripcion:
        return jsonify({"error": f"Faltan campos obligatorios. Recibí: {d}"}), 400

    db_query(
        "INSERT INTO tickets_soporte (empresa_id, contacto, whatsapp, asunto, descripcion, prioridad) VALUES (%s, %s, %s, %s, %s, %s)",
        (empresa_id, contacto, whatsapp, asunto, descripcion, prioridad)
    )

    mensaje = f"🎫 Ticket: {asunto}. Cliente: {contacto}. WhatsApp: {whatsapp}."
    phone = os.environ.get('WHATSAPP_PHONE')
    apikey = os.environ.get('WHATSAPP_APIKEY')
    
    if phone and apikey:
        try:
            url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={mensaje}&apikey={apikey}"
            requests.get(url)
        except Exception as e:
            print(f"Error WhatsApp: {e}")

    registrar_cambio("Ticket Creado", f"Avería reportada por {contacto}")
    return jsonify({"success": True, "message": "Ticket registrado con éxito"})

@app.route('/api/admin/tickets', methods=['GET'])
def listar_tickets_admin():
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
    if not session.get('rol'):
        return jsonify({"message": "No autorizado"}), 401

    d = request.json or {}
    nuevo_estado = d.get('estado', 'Resuelto')

    db_query("UPDATE tickets_soporte SET estado = %s WHERE id = %s", (nuevo_estado, id))
    registrar_cambio("Resolvió Ticket", f"Ticket ID {id} cambiado a estado: {nuevo_estado}")
    return jsonify({"success": True})

@app.route('/api/admin/empresas-soporte', methods=['POST'])
def dar_alta_empresa_soporte():
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
        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}
        
        if 'hero_titulo' not in config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('hero_titulo', 'Servicio Técnico Profesional') ON CONFLICT DO NOTHING")
        if 'mision' not in config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('mision', 'Brindar soporte técnico especializado con honestidad y excelencia.') ON CONFLICT DO NOTHING")
        if 'vision' not in config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('vision', 'Ser la empresa líder en soluciones tecnológicas y seguridad en Costa Rica.') ON CONFLICT DO NOTHING")
        if 'compromiso' not in config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('compromiso', 'Aseguramos la continuidad operativa de tu negocio mediante respuestas rápidas, acuerdos de nivel de servicio (SLA) eficientes y soporte de alta disponibilidad.') ON CONFLICT DO NOTHING")

        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}

        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in servs_raw]
        
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]) if r[2] else 0.0, "imagen": r[3], "categoria": r[4]} for r in prods_raw]
        
        return jsonify({
            "config": config, "servicios": servs, "productos": prods
        })
    except Exception as e:
        return jsonify({"error": "Error interno", "detalles": str(e)}), 500

@app.route('/api/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar_item(tabla, id):
    tablas_permitidas = ['productos', 'servicios', 'socios', 'resenas', 'beneficios', 'clientes_objetivos', 'empresas_recomiendan']
    if tabla in tablas_permitidas:
        db_query(f"DELETE FROM {tabla} WHERE id = %s", (id,))
        registrar_cambio("Eliminó Contenido", f"Se borró el registro con ID {id} de la tabla '{tabla}'")
        return jsonify({"mensaje": "🗑️"})
    return jsonify({"error": "No válida"}), 400


@app.before_request
def asegurarse_db():
    init_db()
    
# ==========================================
# 🏠 DESPACHADOR DE ARCHIVOS RAÍZ (SOLUCIÓN DE HERENCIA VERCEL)
# ==========================================
@app.route('/')
def servir_raiz():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def servir_archivos_sueltos(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)