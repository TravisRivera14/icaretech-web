from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import psycopg2

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

def db_query(query, params=(), fetch=False):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

@app.before_request
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS productos (id SERIAL PRIMARY KEY, nombre TEXT, precio NUMERIC, imagen TEXT, categoria TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS socios (id SERIAL PRIMARY KEY, nombre TEXT, imagen TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS resenas (id SERIAL PRIMARY KEY, cliente TEXT, puesto TEXT, comentario TEXT, imagen_cliente TEXT, estrellas INTEGER)')
        conn.commit()
        conn.close()
    except: pass

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    p = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True)
    s = db_query("SELECT id, icono, titulo, descripcion, imagen FROM servicios", fetch=True)
    return jsonify({
        "productos": [{"id":r[0], "nombre":r[1], "precio":float(r[2]), "imagen":r[3]} for r in p],
        "servicios": [{"id":r[0], "icono":r[1], "titulo":r[2], "descripcion":r[3]} for r in s]
    })

@app.route('/api/productos', methods=['POST'])
def guardar_producto():
    d = request.json
    db_query("INSERT INTO productos (nombre, precio) VALUES (%s, %s)", (d['nombre'], d['precio']))
    return jsonify({"status": "ok"})

@app.route('/api/eliminar/productos/<int:id>', methods=['DELETE'])
def eliminar(id):
    db_query("DELETE FROM productos WHERE id = %s", (id,))
    return jsonify({"status": "deleted"})

@app.route('/')
def index(): return send_from_directory('frontend', 'index.html')

if __name__ == '__main__': app.run()