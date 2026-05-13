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
    c.execute('''CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, precio TEXT, imagen TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (id INTEGER PRIMARY KEY AUTOINCREMENT, icono TEXT, titulo TEXT, descripcion TEXT, imagen TEXT)''')
    conn.commit()
    conn.close()

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True)
    config = {r[0]: r[1] for r in config_raw}
    servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4]} for r in db_query("SELECT id, icono, titulo, descripcion, imagen FROM servicios", fetch=True)]
    prods = [{"id": r[0], "nombre": r[1], "precio": r[2], "imagen": r[3]} for r in db_query("SELECT id, nombre, precio, imagen FROM productos", fetch=True)]
    return jsonify({"config": config, "servicios": servs, "productos": prods})

@app.route('/api/config', methods=['POST'])
def guardar_config():
    data = request.json
    for k, v in data.items():
        exists = db_query("SELECT 1 FROM configuracion WHERE clave = ?", (k,), fetch=True)
        if exists: db_query("UPDATE configuracion SET valor = ? WHERE clave = ?", (v, k))
        else: db_query("INSERT INTO configuracion (clave, valor) VALUES (?, ?)", (k, v))
    return jsonify({"mensaje": "✅ Web actualizada"})

@app.route('/api/servicios', methods=['POST'])
def guardar_servicio():
    d = request.json
    db_query("INSERT INTO servicios (icono, titulo, descripcion, imagen) VALUES (?, ?, ?, ?)", (d['icono'], d['titulo'], d['descripcion'], d.get('imagen', '')))
    return jsonify({"mensaje": "✅ Servicio añadido"})

@app.route('/api/servicios/<int:id>', methods=['PUT'])
def editar_servicio(id):
    d = request.json
    db_query("UPDATE servicios SET icono=?, titulo=?, descripcion=?, imagen=? WHERE id=?", (d['icono'], d['titulo'], d['descripcion'], d.get('imagen',''), id))
    return jsonify({"mensaje": "✅ Servicio actualizado"})

@app.route('/api/productos', methods=['POST'])
def guardar_producto():
    d = request.json
    db_query("INSERT INTO productos (nombre, precio, imagen) VALUES (?, ?, ?)", (d['nombre'], d['precio'], d['imagen']))
    return jsonify({"mensaje": "✅ Producto añadido"})

@app.route('/api/productos/<int:id>', methods=['PUT'])
def editar_producto(id):
    d = request.json
    db_query("UPDATE productos SET nombre=?, precio=?, imagen=? WHERE id=?", (d['nombre'], d['precio'], d['imagen'], id))
    return jsonify({"mensaje": "✅ Producto actualizado"})

@app.route('/api/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar_item(tabla, id):
    db_query(f"DELETE FROM {tabla} WHERE id = ?", (id,))
    return jsonify({"mensaje": "🗑️ Eliminado"})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)