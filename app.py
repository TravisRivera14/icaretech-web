from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, categoria TEXT, precio TEXT, imagen TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (id INTEGER PRIMARY KEY AUTOINCREMENT, icono TEXT, titulo TEXT, descripcion TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS beneficios (id INTEGER PRIMARY KEY AUTOINCREMENT, icono TEXT, titulo TEXT, descripcion TEXT)''')
    # Nueva tabla para pestañas extra
    c.execute('''CREATE TABLE IF NOT EXISTS secciones_extra (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, contenido TEXT)''')
    
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('mision', 'Nuestra misión...')")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('vision', 'Nuestra visión...')")
    conn.commit()
    conn.close()

@app.route('/api/secciones', methods=['GET', 'POST'])
def manejar_secciones():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute("DELETE FROM secciones_extra")
        for s in data:
            c.execute("INSERT INTO secciones_extra (titulo, contenido) VALUES (?, ?)", (s['titulo'], s['contenido']))
        conn.commit()
        return jsonify({"mensaje": "✅ Secciones actualizadas"})
    c.execute("SELECT * FROM secciones_extra")
    res = [{"titulo": r[1], "contenido": r[2]} for r in c.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/productos', methods=['GET', 'POST'])
def manejar_productos():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    if request.method == 'POST':
        d = request.json
        c.execute("INSERT INTO productos (nombre, categoria, precio, imagen) VALUES (?, ?, ?, ?)", (d['nombre'], d['categoria'], d['precio'], d['imagen']))
        conn.commit()
        return jsonify({"mensaje": "✅ Guardado"})
    c.execute("SELECT * FROM productos")
    res = [{"nombre": r[1], "categoria": r[2], "precio": r[3], "imagen": r[4]} for r in c.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/config', methods=['GET', 'POST'])
def manejar_config():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    if request.method == 'POST':
        d = request.json
        for k, v in d.items(): c.execute("UPDATE configuracion SET valor = ? WHERE clave = ?", (v, k))
        conn.commit()
        return jsonify({"mensaje": "✅ Configuración guardada"})
    c.execute("SELECT * FROM configuracion")
    res = {r[0]: r[1] for r in c.fetchall()}
    conn.close()
    return jsonify(res)

@app.route('/api/servicios', methods=['GET', 'POST'])
def manejar_servicios():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute("DELETE FROM servicios")
        for s in data: c.execute("INSERT INTO servicios (icono, titulo, descripcion) VALUES (?, ?, ?)", (s['icono'], s['titulo'], s['descripcion']))
        conn.commit()
        return jsonify({"mensaje": "✅ Servicios guardados"})
    c.execute("SELECT * FROM servicios")
    res = [{"icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in c.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/beneficios', methods=['GET', 'POST'])
def manejar_beneficios():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute("DELETE FROM beneficios")
        for b in data: c.execute("INSERT INTO beneficios (icono, titulo, descripcion) VALUES (?, ?, ?)", (b['icono'], b['titulo'], b['descripcion']))
        conn.commit()
        return jsonify({"mensaje": "✅ Beneficios guardados"})
    c.execute("SELECT * FROM beneficios")
    res = [{"icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in c.fetchall()]
    conn.close()
    return jsonify(res)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)