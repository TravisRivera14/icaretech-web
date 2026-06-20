from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
import random
from datetime import datetime

app = Flask(__name__)
CORS(app, supports_credentials=True)

app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iCareTechCR_Master_Key_2026')
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

# --- ENDPOINTS ---

@app.route('/api/facturacion/emitir', methods=['POST'])
def emitir_factura():
    d = request.json or {}
    cliente_id = d.get('cliente_id')
    lineas = d.get('lineas', [])
    try:
        # Consulta simplificada para evitar errores de null
        consecutivo = "0010000101" + datetime.now().strftime("%H%M%S")
        clave = "506" + datetime.now().strftime("%d%m%y") + "3101000000" + consecutivo + "1" + str(random.randint(10000000, 99999999))
        
        total = sum(float(l['monto_total']) for l in lineas) * 1.13
        
        db_query("""
            INSERT INTO Facturas (Id_Empresa, Id_Cliente, Consecutivo, Clave_50_Digitos, Total_Comprobante, Estado_Hacienda) 
            VALUES (1, %s, %s, %s, %s, 'Pendiente')
        """, (cliente_id, consecutivo, clave, total))
        
        return jsonify({"success": True, "clave": clave})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

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

if __name__ == '__main__':
    app.run(debug=True)