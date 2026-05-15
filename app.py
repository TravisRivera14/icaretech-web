from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

def init_db():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, precio TEXT, imagen TEXT, categoria TEXT DEFAULT 'Otros')''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (id INTEGER PRIMARY KEY AUTOINCREMENT, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS socios (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, imagen TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS resenas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, puesto TEXT, comentario TEXT, imagen_cliente TEXT, estrellas INTEGER DEFAULT 5)''')
    conn.commit()
    conn.close()

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True)
    config = {r[0]: r[1] for r in config_raw}
    servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4]} for r in db_query("SELECT id, icono, titulo, descripcion, imagen FROM servicios", fetch=True)]
    prods = [{"id": r[0], "nombre": r[1], "precio": r[2], "imagen": r[3], "categoria": r[4]} for r in db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True)]
    parts = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in db_query("SELECT id, nombre, imagen FROM socios", fetch=True)]
    reviews = [{"id": r[0], "cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4], "estrellas": r[5]} for r in db_query("SELECT id, cliente, puesto, comentario, imagen_cliente, estrellas FROM resenas", fetch=True)]
    return jsonify({"config": config, "servicios": servs, "productos": prods, "socios": parts, "resenas": reviews})

@app.route('/api/resenas', methods=['POST'])
def guardar_resena():
    d = request.json
    db_query("INSERT INTO resenas (cliente, puesto, comentario, imagen_cliente) VALUES (?, ?, ?, ?)", (d['cliente'], d.get('puesto', ''), d['comentario'], d.get('imagen_cliente', '')))
    return jsonify({"mensaje": "✅"})

# ✅ RUTA DE EDICIÓN PARA RESEÑAS AÑADIDA
@app.route('/api/resenas/<int:id>', methods=['PUT'])
def editar_resena(id):
    d = request.json
    db_query("UPDATE resenas SET cliente=?, puesto=?, comentario=?, imagen_cliente=? WHERE id=?", (d['cliente'], d.get('puesto', ''), d['comentario'], d.get('imagen_cliente',''), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/socios', methods=['POST'])
def guardar_socio():
    d = request.json
    db_query("INSERT INTO socios (nombre, imagen) VALUES (?, ?)", (d['nombre'], d.get('imagen', '')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios', methods=['POST'])
def guardar_servicio():
    d = request.json
    db_query("INSERT INTO servicios (icono, titulo, descripcion, imagen) VALUES (?, ?, ?, ?)", (d['icono'], d['titulo'], d['descripcion'], d.get('imagen', '')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/productos', methods=['POST'])
def guardar_producto():
    d = request.json
    db_query("INSERT INTO productos (nombre, precio, imagen, categoria) VALUES (?, ?, ?, ?)", (d['nombre'], d['precio'], d['imagen'], d.get('categoria', 'Otros')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios/<int:id>', methods=['PUT'])
def editar_servicio(id):
    d = request.json
    db_query("UPDATE servicios SET icono=?, titulo=?, descripcion=?, imagen=? WHERE id=?", (d['icono'], d['titulo'], d['descripcion'], d.get('imagen',''), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/productos/<int:id>', methods=['PUT'])
def editar_producto(id):
    d = request.json
    db_query("UPDATE productos SET nombre=?, precio=?, imagen=?, categoria=? WHERE id=?", (d['nombre'], d['precio'], d['imagen'], d.get('categoria', 'Otros'), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar_item(tabla, id):
    db_query(f"DELETE FROM {tabla} WHERE id = ?", (id,))
    return jsonify({"mensaje": "🗑️"})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)