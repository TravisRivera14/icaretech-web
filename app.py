from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, jsonify
import os
import psycopg2
import requests

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
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, rol VARCHAR(20) NOT NULL CHECK (rol IN ('admin', 'personal')), nombre VARCHAR(100) NOT NULL, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial_cambios (id SERIAL PRIMARY KEY, usuario_id INT NULL, usuario_nombre VARCHAR(50) NOT NULL, accion VARCHAR(100) NOT NULL, detalle TEXT NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # MODIFICACIÓN TÉCNICA: Se comprueba y crea la tabla para las empresas corporativas que reciben soporte técnico
    c.execute('''CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT NOT NULL, imagen TEXT DEFAULT '')''')
    
    # MODIFICACIÓN TÉCNICA: Tabla maestra para la gestión de tickets segmentada por empresa cliente
    c.execute('''CREATE TABLE IF NOT EXISTS tickets_soporte (
                    id SERIAL PRIMARY KEY, 
                    empresa_id INT REFERENCES empresas_recomiendan(id) ON DELETE CASCADE, 
                    contacto VARCHAR(100) NOT NULL, 
                    asunto VARCHAR(200) NOT NULL, 
                    descripcion TEXT NOT NULL, 
                    prioridad VARCHAR(20) NOT NULL, 
                    estado VARCHAR(20) DEFAULT 'Abierto', 
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    c.close()
    conn.close()

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




# ==========================================
# 🇨🇷 MÓDULO DE FACTURACIÓN: CONFIGURACIÓN HACIENDA
# ==========================================

@app.route('/api/admin/configuracion-hacienda', methods=['POST'])
def guardar_configuracion_hacienda():
    """Recibe, procesa y almacena en Neon las credenciales de facturación."""
    # 1. Seguridad: Verificar que el usuario esté autenticado
    if not session.get('rol'):
        return jsonify({"message": "Acceso denegado"}), 403

    usuario_idp = request.form.get('usuario_idp')
    password_idp = request.form.get('password_idp')
    pin_p12 = request.form.get('pin_p12')
    ambiente = request.form.get('ambiente')
    ambiente_produccion = True if ambiente in ['true', 'on', True] else False
    
    # 2. Manejo de archivos múltiples (.p12)
    archivo_p12 = request.files.get('archivo_p12')
    
    # Vinculamos al ID corporativo por defecto si no viene mapeado en el formulario
    id_empresa_actual = request.form.get('id_empresa', 1)

    if not usuario_idp or not password_idp or not pin_p12 or not archivo_p12:
        return jsonify({"success": False, "message": "Todos los campos de Hacienda son requeridos"}), 400

    try:
        # 3. Leer los bytes binarios del archivo de llave (.p12) y pasarlos a una cadena Base64
        contenido_binario = archivo_p12.read()
        import base64
        p12_base64 = base64.b64encode(contenido_binario).decode('utf-8')

        # 4. Inserción o actualización segura en Neon usando la infraestructura existente
        # Revisamos si esa empresa ya posee credenciales vinculadas
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
    """Informa al frontend si la empresa ya completó su registro de llaves."""
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
# 🔐 FASE 3: MOTOR DE AUTENTICACIÓN OAUTH 2.0 CON HACIENDA
# ==========================================

def obtener_oauth_token_hacienda(id_empresa):
    """
    Obtiene un token de acceso activo directamente desde los servidores de Hacienda.
    Desencripta las credenciales de Neon y realiza la petición x-www-form-urlencoded.
    """
    # 1. Traer los datos de configuración de la base de datos
    res = db_query("""
        SELECT hacienda_usuario_idp, hacienda_password_idp, ambiente_produccion 
        FROM configuracionhacienda WHERE id_empresa = %s
    """, (id_empresa,), fetch=True)
    
    if not res:
        raise Exception(f"La empresa con ID {id_empresa} no tiene configuradas sus credenciales de Hacienda.")
    
    usuario_idp = res[0][0]
    password_idp = res[0][1]  # Nota: Si en el futuro aplicas cifrado extra, aquí se desencriptaría
    ambiente_produccion = res[0][2]

    # 2. Definir los endpoints oficiales de Hacienda basados en el ambiente
    if ambiente_produccion:
        url_auth = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token"
    else:
        url_auth = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token"

    # 3. Estructurar el cuerpo de la petición según el estándar de Hacienda (OAuth 2.0)
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
        # 4. Hacer la petición POST al servidor de identidad (IDP) de Hacienda
        response = requests.post(url_auth, data=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            datos_token = response.json()
            # Devolvemos el access_token listo para usarse en las cabeceras de las facturas
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

# Endpoint de prueba interna para verificar que tus credenciales de ATV de verdad funcionan
@app.route('/api/admin/facturacion/probar-conexion/<int:id_empresa>', methods=['GET'])
def probar_conexion_hacienda(id_empresa):
    if not session.get('rol'):
        return jsonify({"message": "Acceso denegado"}), 403
        
    resultado = obtener_oauth_token_hacienda(id_empresa)
    
    if resultado["success"]:
        return jsonify({
            "status": "Conexión Exitosa",
            "mensaje": "Tu servidor de iCarTech CR logró autenticarse correctamente con Hacienda.",
            "token_recibido_recortado": resultado["access_token"][:30] + "..."
        })
    else:
        return jsonify({
            "status": "Error de Autenticación",
            "mensaje": "Hacienda rechazó las credenciales ingresadas.",
            "detalles_tecnicos": resultado
        }), 400
    

# ==========================================
# 📐 FASE 4: GENERACIÓN DE CLAVE DE 50 DÍGITOS Y XML (VERSIÓN 4.4)
# ==========================================
import random
from datetime import datetime
import xml.etree.ElementTree as ET

def calcular_clave_50_digitos(cedula_emisor, consecutivo, situacion="1"):
    """
    Genera la clave de 50 caracteres reglamentaria de Costa Rica.
    cedula_emisor: string numérico (ej. '3101XXXXXX').
    consecutivo: string numérico de 20 dígitos.
    situacion: '1' (Normal), '2' (Contingencia), '3' (Sin internet).
    """
    # 1. Obtener la fecha actual costarricense
    ahora = datetime.now()
    dia = ahora.strftime("%d")
    mes = ahora.strftime("%m")
    ano = ahora.strftime("%y") # Últimos 2 dígitos del año (ej. '26')

    # 2. Limpiar y normalizar la cédula a 12 caracteres (rellena con ceros a la izquierda)
    cedula_limpia = "".join(filter(str.isdigit, str(cedula_emisor)))
    cedula_12 = cedula_limpia.zfill(12)

    # 3. Código de seguridad aleatorio de 8 dígitos
    codigo_seguridad = "".join([str(random.randint(0, 9)) for _ in range(8)])

    # 4. Concatenar según el estándar oficial de Hacienda
    clave = f"506{dia}{mes}{ano}{cedula_12}{consecutivo}{situacion}{codigo_seguridad}"
    
    if len(clave) != 50:
        raise Exception(f"Error crítico en el cálculo de la clave. Longitud obtenida: {len(clave)} de 50.")
    return clave


def generar_xml_factura_44(datos_factura, lineas_detalle):
    """
    Construye la estructura de texto plano XML válida para el Ministerio de Hacienda v4.4.
    datos_factura: dict con llaves ('clave', 'consecutivo', 'condicion_venta', 'medio_pago', 'emisor_nombre', 'emisor_cedula', 'cliente_nombre', 'cliente_cedula', etc.)
    lineas_detalle: list de dicts con el desglose de productos/servicios e impuestos.
    """
    # Definir los Namespaces reglamentarios de la versión 4.4 de Hacienda
    NS_FACTURA = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturelectronica"
    
    # Raíz del XML
    root = ET.Element("FacturaElectronica", {
        "xmlns": NS_FACTURA,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": f"{NS_FACTURA} https://www.hacienda.go.cr/ATV/ComprobanteElectronico/v4.4/facturelectronica.xsd"
    })

    # Elementos principales del encabezado
    ET.SubElement(root, "Clave").text = datos_factura['clave']
    ET.SubElement(root, "CodigoActividad").text = datos_factura.get('codigo_actividad', '620201') # Código de soporte/IT por defecto
    ET.SubElement(root, "NumeroConsecutivo").text = datos_factura['consecutivo']
    ET.SubElement(root, "FechaEmision").text = datetime.now().isoformat()[:-3] + "-06:00" # Formato ISO con zona horaria CR
    
    # Nodo Emisor (Tu cliente corporativo o iCarTech CR)
    emisor = ET.SubElement(root, "Emisor")
    ET.SubElement(emisor, "Nombre").text = datos_factura['emisor_nombre']
    id_emisor = ET.SubElement(emisor, "Identificacion")
    ET.SubElement(id_emisor, "Tipo").text = datos_factura.get('emisor_tipo_cedula', '02') # '02' Jurídica, '01' Física
    ET.SubElement(id_emisor, "Numero").text = datos_factura['emisor_cedula']
    ET.SubElement(emisor, "CorreoElectronico").text = datos_factura.get('emisor_correo', 'soporte@icartech.cr')

    # Nodo Receptor (A quién le vendes el servicio)
    receptor = ET.SubElement(root, "Receptor")
    ET.SubElement(receptor, "Nombre").text = datos_factura['cliente_nombre']
    id_receptor = ET.SubElement(receptor, "Identificacion")
    ET.SubElement(id_receptor, "Tipo").text = datos_factura.get('cliente_tipo_cedula', '01')
    ET.SubElement(id_receptor, "Numero").text = datos_factura['cliente_cedula']
    ET.SubElement(receptor, "CorreoElectronico").text = datos_factura.get('cliente_correo')

    ET.SubElement(root, "CondicionVenta").text = datos_factura.get('condicion_venta', '01') # 01 = Contado
    ET.SubElement(root, "MedioPago").text = datos_factura.get('medio_pago', '04') # 04 = Transferencia

    # Desglose de Líneas de Factura (El detalle físico)
    detalle_nodo = ET.SubElement(root, "DetalleServicio")
    
    total_serv_gravados = 0.0
    total_iva = 0.0

    for idx, linea in enumerate(lineas_detalle, start=1):
        linea_nodo = ET.SubElement(detalle_nodo, "LineaDetalle")
        ET.SubElement(linea_nodo, "NumeroLinea").text = str(idx)
        ET.SubElement(linea_nodo, "Codigo").text = linea['codigo_cabys'] # Código obligatorio CAByS de 13 dígitos
        ET.SubElement(linea_nodo, "Cantidad").text = f"{float(linea['cantidad']):.3f}"
        ET.SubElement(linea_nodo, "UnidadMedida").text = linea.get('unidad_medida', 'Sp') # Sp = Servicios Profesionales
        ET.SubElement(linea_nodo, "Detalle").text = linea['descripcion']
        ET.SubElement(linea_nodo, "PrecioUnitario").text = f"{float(linea['precio_unitario']):.5f}"
        ET.SubElement(linea_nodo, "MontoTotal").text = f"{float(linea['monto_total']):.5f}"
        ET.SubElement(linea_nodo, "SubTotal").text = f"{float(linea['monto_total']):.5f}"

        # Cálculo interno del IVA de la línea (13% estándar de Costa Rica)
        monto_impuesto = float(linea['monto_total']) * 0.13
        total_serv_gravados += float(linea['monto_total'])
        total_iva += monto_impuesto

        impuesto_nodo = ET.SubElement(linea_nodo, "Impuesto")
        ET.SubElement(impuesto_nodo, "Codigo").text = "01" # 01 = IVA
        ET.SubElement(impuesto_nodo, "CodigoTarifa").text = "08" # 08 = Tarifa General 13%
        ET.SubElement(impuesto_nodo, "Tarifa").text = "13.00"
        ET.SubElement(impuesto_nodo, "Monto").text = f"{monto_impuesto:.5f}"
        
        ET.SubElement(linea_nodo, "MontoTotalLinea").text = f"{(float(linea['monto_total']) + monto_impuesto):.5f}"

    # Resumen de los Totales Finales de la Factura
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

    # Retornar el string XML limpio decodificado en UTF-8
    return ET.tostring(root, encoding="utf-8").decode("utf-8")


# ==========================================
# 🚀 FASE 5: ENVÍO ASÍNCRONO Y RECEPCIÓN DE COMPROBANTES
# ==========================================
import base64
import json

def enviar_factura_hacienda(id_empresa, datos_factura, xml_string):
    """
    Toma el XML, lo codifica en Base64 y lo envía al API de Recepción de Hacienda.
    """
    # 1. Obtener el Token OAuth de la Fase 3 y ver el ambiente
    token_data = obtener_oauth_token_hacienda(id_empresa)
    if not token_data["success"]:
        return {"success": False, "message": "Error de autenticación: " + token_data["error_detalle"]}
    
    token = token_data["access_token"]
    
    # Revisar ambiente consultando Neon de nuevo
    res_empresa = db_query("SELECT ambiente_produccion, cedula_juridica FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    ambiente_produccion = res_empresa[0][0]
    cedula_emisor = res_empresa[0][1]

    # Definir la URL de recepción correcta
    if ambiente_produccion:
        url_recepcion = "https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion"
    else:
        url_recepcion = "https://api-sandbox.comprobanteselectronicos.go.cr/recepcion/v1/recepcion"

    # 2. Convertir el XML completo a Base64 string (Exigencia estricta de Hacienda)
    xml_bytes = xml_string.encode('utf-8')
    xml_base64 = base64.b64encode(xml_bytes).decode('utf-8')

    # 3. Construir el JSON Payload con la estructura legal requerida
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
        # 4. Enviar el comprobante (POST)
        response = requests.post(url_recepcion, data=json.dumps(payload), headers=headers, timeout=10)
        
        # Hacienda responde con un 202 Accepted si el XML es recibido correctamente para análisis
        if response.status_code in [202, 200]:
            return {"success": True, "message": "Factura recibida por Hacienda en proceso de validación."}
        else:
            return {"success": False, "message": f"Hacienda rechazó el paquete inicial ({response.status_code}): {response.text}"}
            
    except Exception as e:
        return {"success": False, "message": f"Error de conexión con el API de Recepción: {str(e)}"}


@app.route('/api/admin/facturacion/consultar-estado/<int:id_empresa>/<string:clave>', methods=['GET'])
def consultar_estado_factura(id_empresa, clave):
    """
    Ruta API para consultar si Hacienda finalmente Aceptó o Rechazó una factura específica.
    """
    if not session.get('rol'):
        return jsonify({"message": "Acceso denegado"}), 403

    # Ver el ambiente de la empresa
    res_empresa = db_query("SELECT ambiente_produccion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    if not res_empresa:
        return jsonify({"error": "Empresa no configurada"}), 400
        
    ambiente_produccion = res_empresa[0][0]

    # Conseguir Token activo
    token_data = obtener_oauth_token_hacienda(id_empresa)
    if not token_data["success"]:
        return jsonify({"error": "No se pudo obtener el token de acceso"}), 500

    # URL de consulta (Se le pega la clave de 50 dígitos al final)
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
            estado_final = datos_respuesta.get("ind-estado", "Pendiente") # 'aceptado' o 'rechazado'
            
            # Actualizamos el estado real en tu base de datos de Neon
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
    """
    Controlador principal que une todas las fases: 
    Recibe el JSON de la interfaz, procesa la clave, arma el XML y lo envía a Hacienda.
    """
    # 1. Protección de ruta: Validar inicio de sesión
    if not session.get('rol'):
        return jsonify({"success": False, "message": "Acceso denegado. Inicie sesión."}), 403

    d = request.json or {}
    cliente_id = d.get('cliente_id')
    condicion_venta = d.get('condicion_venta', '01')
    medio_pago = d.get('medio_pago', '04')
    lineas_frontend = d.get('lineas', [])

    # Id de empresa vinculada al usuario (Soporte Multi-tenant)
    id_empresa_actual = 1 

    if not cliente_id or not lineas_frontend:
        return jsonify({"success": False, "message": "Faltan datos esenciales (Cliente o Líneas de detalle)"}), 400

    try:
        # 2. Consultar base de datos en Neon para traer datos del Emisor (Empresa)
        res_emisor = db_query("SELECT cedula_juridica, nombre_empresa, correo FROM empresa WHERE id_empresa = %s", (id_empresa_actual,), fetch=True)
        if not res_emisor:
            return jsonify({"success": False, "message": "Empresa emisora no registrada o incompleta en el sistema."}), 400
        
        # 3. Consultar Neon para traer los datos del Receptor (Cliente)
        res_cliente = db_query("SELECT cedula, nombre_completo, correo FROM clientes WHERE id_cliente = %s", (cliente_id,), fetch=True)
        if not res_cliente:
            return jsonify({"success": False, "message": "El cliente seleccionado no existe en la base de datos."}), 400

        # Mapeo estructurado para el generador XML
        emisor_datos = {"cedula": res_emisor[0][0], "nombre": res_emisor[0][1], "correo": res_emisor[0][2]}
        cliente_datos = {"cedula": res_cliente[0][0], "nombre": res_cliente[0][1], "correo": res_cliente[0][2]}

        # 4. Calcular el Número Consecutivo Interno (Requisito de 20 dígitos de Hacienda)
        # Para desarrollo, generamos uno correlativo basado en la hora actual
        consecutivo_sistema = "0010000101" + datetime.now().strftime("%H%M%S").zfill(10)

        # 5. FASE 4: Calcular la Clave País de 50 dígitos
        clave_50 = calcular_clave_50_digitos(emisor_datos["cedula"], consecutivo_sistema)

        # Totales agregados para persistencia
        total_serv_gravados = sum(float(l['monto_total']) for l in lineas_frontend)
        total_iva = total_serv_gravados * 0.13
        total_comprobante = total_serv_gravados + total_iva

        # 6. PERSISTENCIA EN NEON: Insertar el encabezado de la factura en estado 'Pendiente'
        # Usamos nombres exactos de columnas como se crearon en tu Neon
        db_query("""
            INSERT INTO Facturas (
                Id_Empresa, Id_Cliente, Consecutivo, Clave_50_Digitos, 
                Condicion_Venta, Medio_Pago, Total_Servicios_Gravados, Total_Impuesto, Total_Comprobante, Estado_Hacienda
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendiente')
        """, (id_empresa_actual, cliente_id, consecutivo_sistema, clave_50, condicion_venta, medio_pago, total_serv_gravados, total_iva, total_comprobante))

        # 7. FASE 4 (XML): Estructurar el diccionario y construir el archivo XML 4.4 plano
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

        # 8. FASE 5 (Envío): Despachar de forma asíncrona hacia los servidores de Hacienda
        resultado_envio = enviar_factura_hacienda(id_empresa_actual, datos_xml_maestro, xml_generado)

        if resultado_envio["success"]:
            return jsonify({
                "success": True,
                "message": "Factura procesada con éxito",
                "clave": clave_50,
                "consecutivo": consecutivo_sistema
            })
        else:
            # Si Hacienda falla al recibir el paquete, cambiamos el estado en Neon a 'Rechazado' con el log
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
    d = request.json or {}
    
    # DEBUG: Esto imprimirá los datos en los logs de Vercel para que veamos qué llega
    print(f"DATOS_RECIBIDOS_EN_BACKEND: {d}")

    # Extraemos con valores por defecto para no romper el código si algo falta
    empresa_id = d.get('empresa_id')
    contacto = d.get('contacto')
    whatsapp = d.get('whatsapp') 
    asunto = d.get('asunto')
    descripcion = d.get('descripcion')
    prioridad = d.get('prioridad', 'Alta')

    # Validamos solo lo esencial, dejando de lado los que a veces llegan como None
    if not contacto or not asunto or not descripcion:
        return jsonify({"error": f"Faltan campos obligatorios. Recibí: {d}"}), 400

    # Inserción a BD
    db_query(
        "INSERT INTO tickets_soporte (empresa_id, contacto, whatsapp, asunto, descripcion, prioridad) VALUES (%s, %s, %s, %s, %s, %s)",
        (empresa_id, contacto, whatsapp, asunto, descripcion, prioridad)
    )

    # Lógica de Notificación WhatsApp
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

        # Modificación para evitar vaciar constantemente si ya existen datos cargados dinámicamente
        beneficios_existentes = db_query("SELECT COUNT(*) FROM beneficios", fetch=True)
        if beneficios_existentes and beneficios_existentes[0][0] == 0:
            ventajas_defecto = [
                ("Técnicos Certificados", "Tu infraestructura y equipos son manipulados exclusivamente por profesionales expertos.", "fas fa-user-check"),
                ("Repuestos Originales", "Utilizamos componentes genuinos y de grado premium para asegurar la máxima durabilidad.", "fas fa-shield-alt"),
                ("Transparencia Total", "Sin costos ocultos ni sorpresas. Te explicamos el problema y validamos el presupuesto antes de proceder.", "fas fa-handshake"),
                ("Atención personalizada", "Ofrecemos soluciones directas y personalizadas para cada cliente.", "fas fa-user-heart"),
                ("Soluciones integrales en tecnología", "Soporte, instalaciones y asesoría global para tu infraestructura.", "fas fa-laptop-code"),
                ("Equipos y herramientas modernas", "Trabajamos con instrumental de vanguardia para diagnósticos precisos.", "fas fa-tools"),
                ("Servicio confiable y profesional", "Cuentan con personal capacitado que garantiza ética, puntualidad y cumplimiento en su trabajo.", "fas fa-award"),
                ("Soporte técnico especializado", "Ofrecen asistencia experta para resolver problemas complejos de hardware o software.", "fas fa-microchip"),
                ("Experiencia en seguridad electrónica", "Tienen conocimientos específicos en sistemas como cámaras de vigilancia, alarmas y controles de acceso.", "fas fa-video"),
                ("Compromiso con la calidad", "Se enfocan en realizar trabajos bien hechos que aseguren la satisfacción del cliente a largo plazo.", "fas fa-star"),
                ("Cobertura a domicilio en Costa Rica", "Brindan comodidad al desplazarse a tu casa o empresa en cualquier parte del país para realizar el servicio.", "fas fa-map-marked-alt"),
                ("Repuestos genéricos", "Ofrecemos piezas de alta compatibilidad y bajo costo, ideales para optimizar tu presupuesto sin perder funcionalidad.", "fas fa-exchange-alt")
            ]
            for titulo, desc, icono in ventajas_defecto:
                db_query("INSERT INTO beneficios (titulo, descripcion, icono) VALUES (%s, %s, %s)", (titulo, desc, icono))

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

        return jsonify({
            "config": config, "servicios": servs, "productos": prods, "socios": parts, "resenas": reviews, "beneficios": beneficios, "objetivos": objetivos, "empresas": empresas
        })
    except Exception as e:
        return jsonify({"error": "Error interno", "detalles": str(e)}), 500

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

@app.route('/api/socios', methods=['POST'])
def guardar_socio():
    d = request.json or {}
    db_query("INSERT INTO socios (nombre, imagen) VALUES (%s, %s)", (d.get('nombre', 'Socio'), d.get('imagen', '')))
    registrar_cambio("Añadió Socio Comercial", f"Se registró el socio: {d.get('nombre', '')}")
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
@app.before_request
def asegurarse_db():
    # Esto corre antes de CADA petición, lo cual es seguro y garantiza que las tablas existan.
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5001)