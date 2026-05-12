from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app) # Permite que el HTML hable con este servidor

def init_db():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  nombre TEXT, categoria TEXT, precio TEXT, imagen TEXT)''')
    conn.commit()
    conn.close()

@app.route('/api/productos', methods=['POST'])
def agregar_producto():
    data = request.json
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    c.execute("INSERT INTO productos (nombre, categoria, precio, imagen) VALUES (?, ?, ?, ?)",
              (data['nombre'], data['categoria'], data['precio'], data['imagen']))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "✅ Producto guardado en la base de datos"}), 201

@app.route('/api/productos', methods=['GET'])
def obtener_productos():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    c.execute("SELECT * FROM productos")
    productos = [{"id": row[0], "nombre": row[1], "categoria": row[2], "precio": row[3], "imagen": row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify(productos)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)