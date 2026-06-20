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
CORS(app, supports_credentials=True)

# CONFIGURACIONES DE SEGURIDAD
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_HTTPONLY=True
)

# Conexión a Neon
DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON')

def db_query(query, params=(), fetch=False):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    c.close()
    conn.close()
    return res

# ==========================================
# 🇨🇷 LÓGICA HACIENDA (Helpers)
# ==========================================

def calcular_clave_50_digitos(cedula_emisor, consecutivo, situacion="1"):
    ahora = datetime.now()
    dia, mes, ano = ahora.strftime("%d"), ahora.strftime("%m"), ahora.strftime("%y")
    cedula_12 = "".join(filter(str.isdigit, str(cedula_emisor))).zfill(12)
    codigo_seguridad = "".join([str(random.randint(0, 9)) for _ in range(8)])
    return f"506{dia}{mes}{ano}{cedula_12}{consecutivo}{situacion}{codigo_seguridad}"

def obtener_oauth_token_hacienda(id_empresa):
    res = db_query("SELECT hacienda_usuario_idp, hacienda_password_idp, ambiente_produccion FROM configuracionhacienda WHERE id_empresa = %s", (id_empresa,), fetch=True)
    if not res: raise Exception("Credenciales no configuradas")
    u_idp, p_idp, prod = res[0]
    url = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token" if prod else "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token"
    payload = {'grant_type': 'password', 'client_id': 'api-prod' if prod else 'api-stag', 'username': u_idp, 'password': p_idp}
    response = requests.post(url, data=payload, timeout=10)
    return response.json().get("access_token")

# ==========================================
# 🚀 ENDPOINT PRINCIPAL CORREGIDO
# ==========================================

@app.route('/api/facturacion/emitir', methods=['POST'])
def emitir_factura_electronica_api():
    d = request.json or {}
    cliente_id = d.get('cliente_id')
    lineas = d.get('lineas', [])
    id_empresa = 1 

    try:
        # Obtener datos base
        emisor = db_query("SELECT cedula_juridica, nombre_empresa, correo FROM empresa WHERE id_empresa = %s", (id_empresa,), fetch=True)
        cliente = db_query("SELECT cedula, nombre_completo, correo FROM clientes WHERE id_cliente = %s", (cliente_id,), fetch=True)
        
        if not emisor or not cliente: return jsonify({"success": False, "message": "Datos no encontrados"}), 400

        # Crear Clave
        consecutivo = "0010000101" + datetime.now().strftime("%H%M%S")
        clave = calcular_clave_50_digitos(emisor[0][0], consecutivo)
        
        total_serv = sum(float(l['monto_total']) for l in lineas)
        total_iva = total_serv * 0.13

        # Insertar en BD
        db_query("""
            INSERT INTO Facturas (Id_Empresa, Id_Cliente, Consecutivo, Clave_50_Digitos, Total_Comprobante, Estado_Hacienda) 
            VALUES (%s, %s, %s, %s, %s, 'Pendiente')
        """, (id_empresa, cliente_id, consecutivo, clave, total_serv + total_iva))

        return jsonify({"success": True, "clave": clave, "consecutivo": consecutivo})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==========================================
# 🛠️ RUTAS RESTO DE LA APP (Tickets, Login, Todo)
# ==========================================

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    prods = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
    return jsonify({"productos": [{"id": r[0], "nombre": r[1], "precio": float(r[2]), "imagen": r[3], "categoria": r[4]} for r in prods]})

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    res = db_query("SELECT id, usuario, password_hash, rol, nombre FROM usuarios WHERE usuario = %s", (d.get('usuario'),), fetch=True)
    if res and check_password_hash(res[0][2], d.get('password')):
        session.update({'user_id': res[0][0], 'rol': res[0][3], 'nombre': res[0][4]})
        return jsonify({"success": True, "rol": res[0][3]})
    return jsonify({"success": False}), 401

@app.route('/api/tickets', methods=['POST'])
def crear_ticket():
    d = request.json or {}
    db_query("INSERT INTO tickets_soporte (contacto, asunto, descripcion, prioridad) VALUES (%s, %s, %s, %s)", 
             (d.get('contacto'), d.get('asunto'), d.get('descripcion'), d.get('prioridad', 'Alta')))
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(debug=True)