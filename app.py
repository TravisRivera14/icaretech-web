from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_mail import Mail, Message
import os
import psycopg2

app = Flask(__name__)
CORS(app)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'TU_CORREO@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'TU_CONTRASEÑA')
mail = Mail(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

def db_query(query, params=(), fetch=False):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    tablas = [
        "CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC DEFAULT 0, imagen TEXT, categoria TEXT)",
        "CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)",
        "CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT, proceso TEXT, beneficios TEXT)",
        "CREATE TABLE IF NOT EXISTS resenas (id SERIAL PRIMARY KEY, cliente TEXT, puesto TEXT, comentario TEXT, imagen_cliente TEXT)",
        "CREATE TABLE IF NOT EXISTS beneficios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS clientes_objetivos (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT)",
        "CREATE TABLE IF NOT EXISTS empresas_recomiendan (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT)",
        "CREATE TABLE IF NOT EXISTS socios (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT)"
    ]
    for sql in tablas: c.execute(sql)
    conn.commit()
    conn.close()

init_db()

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        config = {r[0]: r[1] for r in db_query("SELECT clave, valor FROM configuracion", fetch=True) or []}
        servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in db_query("SELECT * FROM servicios", fetch=True) or []]
        prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]), "imagen": r[3], "categoria": r[4]} for r in db_query("SELECT * FROM productos", fetch=True) or []]
        return jsonify({"config": config, "servicios": servs, "productos": prods})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)