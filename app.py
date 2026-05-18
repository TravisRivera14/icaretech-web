from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import psycopg2

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# Variable de conexión automática de Neon en Vercel
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
    """Crea las tablas de forma segura si no existen usando sintaxis nativa de Postgres."""
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS productos (
        id SERIAL PRIMARY KEY, 
        nombre TEXT, 
        precio NUMERIC DEFAULT 0, 
        imagen TEXT, 
        categoria TEXT DEFAULT 'Otros'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY, 
        valor TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS servicios (
        id SERIAL PRIMARY KEY, 
        icono TEXT, 
        titulo TEXT, 
        descripcion TEXT, 
        imagen TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS socios (
        id SERIAL PRIMARY KEY, 
        nombre TEXT, 
        imagen TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS resenas (
        id SERIAL PRIMARY KEY, 
        cliente TEXT, 
        puesto TEXT, 
        comentario TEXT, 
        imagen_cliente TEXT, 
        estrellas INTEGER DEFAULT 5
    )''')
    conn.commit()
    conn.close()

# ✅ SOLUCIÓN PARA VERCEL: Garantiza que las tablas existan en Neon al recibir la primera visita
@app.before_request
def antes_de_la_peticion():
    try:
        init_db()
    except Exception as e:
        print(f"Error inicializando la base de datos: {e}")

@app.route('/api/todo', methods=['GET'])
def obtener_todo():
    try:
        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}
        
        # --- AUTO-RELLENO DE RESPALDO SI LA BASE DE DATOS DE NEON ESTÁ VACÍA ---
        if not config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('hero_titulo', 'Servicio Técnico Profesional') ON CONFLICT DO NOTHING")
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('mision', 'Brindar soporte técnico especializado con honestidad y excelencia.') ON CONFLICT DO NOTHING")
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('vision', 'Ser la empresa líder en soluciones tecnológicas y seguridad en Costa Rica.') ON CONFLICT DO NOTHING")
            config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
            config = {r[0]: r[1] for r in config_raw}
        # ---------------------------------------------------------------------

        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen FROM servicios", fetch=True) or []
        servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4]} for r in servs_raw]
        
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        # Convertimos el precio a float de forma segura para evitar romper el formato de moneda de JS
        prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]) if r[2] else 0.0, "imagen": r[3], "categoria": r[4]} for r in prods_raw]
        
        parts_raw = db_query("SELECT id, nombre, imagen FROM socios", fetch=True) or []
        parts = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in parts_raw]
        
        reviews_raw = db_query("SELECT id, cliente, puesto, comentario, imagen_cliente, estrellas FROM resenas", fetch=True) or []
        reviews = [{"id": r[0], "cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4], "estrellas": r[5]} for r in reviews_raw]
        
        return jsonify({
            "config": config, 
            "servicios": servs, 
            "productos": prods, 
            "socios": parts, 
            "resenas": reviews
        })
    except Exception as e:
        return jsonify({"error": "Error interno al procesar los datos", "detalles": str(e)}), 500

@app.route('/api/config', methods=['POST'])
def guardar_config():
    d = request.json or {}
    if 'hero_titulo' in d:
        db_query("INSERT INTO configuracion (clave, valor) VALUES ('hero_titulo', %s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor", (d['hero_titulo'],))
    if 'mision' in d:
        db_query("INSERT INTO configuracion (clave, valor) VALUES ('mision', %s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor", (d['mision'],))
    if 'vision' in d:
        db_query("INSERT INTO configuracion (clave, valor) VALUES ('vision', %s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor", (d['vision'],))
    return jsonify({"mensaje": "✅"})

@app.route('/api/resenas', methods=['POST'])
def guardar_resena():
    d = request.json or {}
    db_query("INSERT INTO resenas (cliente, puesto, comentario, imagen_cliente) VALUES (%s, %s, %s, %s)", (d.get('cliente', 'Anónimo'), d.get('puesto', ''), d.get('comentario', ''), d.get('imagen_cliente', '')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/resenas/<int:id>', methods=['PUT'])
def editar_resena(id):
    d = request.json or {}
    db_query("UPDATE resenas SET cliente=%s, puesto=%s, comentario=%s, imagen_cliente=%s WHERE id=%s", (d.get('cliente', 'Anónimo'), d.get('puesto', ''), d.get('comentario', ''), d.get('imagen_cliente',''), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/socios', methods=['POST'])
def guardar_socio():
    d = request.json or {}
    db_query("INSERT INTO socios (nombre, imagen) VALUES (%s, %s)", (d.get('nombre', 'Socio'), d.get('imagen', '')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios', methods=['POST'])
def guardar_servicio():
    d = request.json or {}
    db_query("INSERT INTO servicios (icono, titulo, descripcion, imagen) VALUES (%s, %s, %s, %s)", (d.get('icono', '⚙'), d.get('titulo', ''), d.get('descripcion', ''), d.get('imagen', '')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/productos', methods=['POST'])
def guardar_producto():
    d = request.json or {}
    precio = d.get('precio', 0)
    try: precio = float(precio) if precio else 0
    except: precio = 0
    db_query("INSERT INTO productos (nombre, precio, imagen, categoria) VALUES (%s, %s, %s, %s)", (d.get('nombre', ''), precio, d.get('imagen', ''), d.get('categoria', 'Otros')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/servicios/<int:id>', methods=['PUT'])
def editar_servicio(id):
    d = request.json or {}
    db_query("UPDATE servicios SET icono=%s, titulo=%s, descripcion=%s, imagen=%s WHERE id=%s", (d.get('icono', '⚙'), d.get('titulo', ''), d.get('descripcion', ''), d.get('imagen',''), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/productos/<int:id>', methods=['PUT'])
def editar_producto(id):
    d = request.json or {}
    precio = d.get('precio', 0)
    try: precio = float(precio) if precio else 0
    except: precio = 0
    db_query("UPDATE productos SET nombre=%s, precio=%s, imagen=%s, categoria=%s WHERE id=%s", (d.get('nombre', ''), precio, d.get('imagen',''), d.get('categoria', 'Otros'), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar_item(tabla, id):
    # Restringimos a tablas que usan llaves numéricas 'id'
    tablas_permitidas = ['productos', 'servicios', 'socios', 'resenas']
    if tabla in tablas_permitidas:
        db_query(f"DELETE FROM {tabla} WHERE id = %s", (id,))
        return jsonify({"mensaje": "🗑️"})
    return jsonify({"error": "Tabla no válida o no eliminable por ID"}), 400

# --- MANEJO DE FRONTEND EN VERCEL ---
@app.route('/')
def serve_frontend():
    return send_from_directory('frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('frontend', path)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)