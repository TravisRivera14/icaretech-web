from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, categoria TEXT, precio TEXT, imagen TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, icono TEXT, titulo TEXT, descripcion TEXT)''')
    
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('mision', 'Nuestra misión es brindar soporte técnico de alta calidad...')")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('vision', 'Ser líderes en soluciones tecnológicas y seguridad...')")
    
    c.execute("SELECT COUNT(*) FROM servicios")
    if c.fetchone()[0] == 0:
        servs = [
            ('📹', 'Cámaras de Seguridad', 'Sistemas de vigilancia inteligentes para tu hogar.'),
            ('💻', 'Soporte Computadoras', 'Reparación y mantenimiento preventivo profesional.'),
            ('📱', 'Servicio Apple', 'Especialistas en iPhone, iPad y Mac.'),
            ('🌐', 'Desarrollo Web', 'Creamos tu presencia digital a medida.')
        ]
        c.executemany("INSERT INTO servicios (icono, titulo, descripcion) VALUES (?, ?, ?)", servs)
    
    conn.commit()
    conn.close()

@app.route('/api/productos', methods=['GET', 'POST'])
def manejar_productos():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    if request.method == 'POST':
        d = request.json
        c.execute("INSERT INTO productos (nombre, categoria, precio, imagen) VALUES (?, ?, ?, ?)",
                  (d['nombre'], d['categoria'], d['precio'], d['imagen']))
        conn.commit()
        return jsonify({"mensaje": "✅ Producto guardado"}), 201
    c.execute("SELECT * FROM productos")
    res = [{"id": r[0], "nombre": r[1], "categoria": r[2], "precio": r[3], "imagen": r[4]} for r in c.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/config', methods=['GET', 'POST'])
def manejar_config():
    conn = sqlite3.connect('inventario.db')
    c = conn.cursor()
    if request.method == 'POST':
        d = request.json
        for k, v in d.items():
            c.execute("UPDATE configuracion SET valor = ? WHERE clave = ?", (v, k))
        conn.commit()
        return jsonify({"mensaje": "✅ Textos actualizados"})
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
        for s in data:
            c.execute("INSERT INTO servicios (icono, titulo, descripcion) VALUES (?, ?, ?)", 
                      (s['icono'], s['titulo'], s['descripcion']))
        conn.commit()
        return jsonify({"mensaje": "✅ Servicios actualizados"})
    c.execute("SELECT * FROM servicios")
    res = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in c.fetchall()]
    conn.close()
    return jsonify(res)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)