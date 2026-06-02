from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import psycopg2

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# Cambiamos la lectura a tu variable manual independiente libre de poolers
DATABASE_URL = os.environ.get('CONEXION_DIRECTA_NEON')

if DATABASE_URL:
    # Asegurar el protocolo correcto requerido por psycopg2
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def db_query(query, params=(), fetch=False):
    # Conexión configurada con soporte SSL obligatorio para Neon
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

def init_db():
    """Crea las tablas de forma segura si no existen e inyecta columnas faltantes."""
    # Conexión configurada con soporte SSL obligatorio para Neon
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
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
        imagen TEXT,
        proceso TEXT,
        beneficios TEXT
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
    c.execute('''CREATE TABLE IF NOT EXISTS beneficios (
        id SERIAL PRIMARY KEY,
        icono TEXT DEFAULT 'fas fa-check',
        titulo TEXT,
        descripcion TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS clientes_objetivos (
        id SERIAL PRIMARY KEY,
        icono TEXT DEFAULT 'fas fa-bullseye',
        titulo TEXT,
        descripcion TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS empresas_recomiendan (
        id SERIAL PRIMARY KEY,
        nombre TEXT,
        imagen TEXT
    )''')
    conn.commit()
    conn.close()

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
        
        if 'hero_titulo' not in config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('hero_titulo', 'Servicio Técnico Profesional') ON CONFLICT DO NOTHING")
        if 'mision' not in config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('mision', 'Brindar soporte técnico especializado con honestidad y excelencia.') ON CONFLICT DO NOTHING")
        if 'vision' not in config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('vision', 'Ser la empresa líder en soluciones tecnológicas y seguridad en Costa Rica.') ON CONFLICT DO NOTHING")
        if 'compromiso' not in config:
            db_query("INSERT INTO configuracion (clave, valor) VALUES ('compromiso', 'Aseguramos la continuidad operativa de tu negocio mediante respuestas rápidas, acuerdos de nivel de servicio (SLA) eficientes y soporte de alta disponibilidad.') ON CONFLICT DO NOTHING")

        # MODIFICACIÓN DE ALINEACIÓN: Validamos si existe la cadena con el punto final para limpiar la tabla y forzar el re-sembrado correcto
        tiene_registro_invalido = db_query("SELECT COUNT(*) FROM beneficios WHERE titulo = 'Atención personalizada.'", fetch=True)
        beneficios_existentes = db_query("SELECT COUNT(*) FROM beneficios", fetch=True)
        
        if (beneficios_existentes and beneficios_existentes[0][0] < 12) or (tiene_registro_invalido and tiene_registro_invalido[0][0] > 0):
            # Eliminación dirigida para forzar la actualización limpia con el texto sanitizado
            db_query("DELETE FROM beneficios")
            
            ventajas_defecto = [
                ("Técnicos Certificados", "Tu infraestructura y equipos son manipulados exclusivamente por profesionales expertos.", "fas fa-user-check"),
                ("Repuestos Originales", "Utilizamos componentes genuinos y de grado premium para asegurar la máxima durabilidad.", "fas fa-shield-alt"),
                ("Transparencia Total", "Sin costos ocultos ni sorpresas. Te explicamos el problema y validamos el presupuesto antes de proceder.", "fas fa-handshake"),
                ("Atención personalizada", "Ofrecemos soluciones directas y personalizadas para cada cliente.", "fas fa-user-heart"),
                ("Soluciones integrales en tecnología", "Soporte, instalaciones y asesoría global para tu infraestructura.", "fas fa-laptop-code"),
                ("Equipos y herramientas modernas", "Trabajamos con instrumental de vanguardia para diagnósticos precisos.", "fas fa-tools"),
                ("Servicio confiable y profesional", "Cuentan con personal capacitado que garantiza ética, puntualidad y cumplimiento en su trabajo.", "fas fa-award"),
                ("Soporte técnico especializado", "Ofrecen asistencia experta para resolver problemas complejos de hardware o software.", "fas fa-microchip"),
                ("Experiencia en seguridad electrónica", "Tienen conocimientos específicos en sistemas como cámaras de vigilancia, alarmas y controles de acceso.", "fas fa-video"),
                ("Compromiso con la calidad", "Se enfocan en realizar trabajos bien hechos que aseguren la satisfacción del cliente a largo plazo.", "fas fa-star"),
                ("Cobertura a domicilio en Costa Rica", "Brindan comodidad al desplazarse a tu casa o empresa en cualquier parte del país para realizar el servicio.", "fas fa-map-marked-alt"),
                ("Repuestos genéricos", "Ofrecemos piezas de alta compatibilidad y bajo costo, ideales para optimizar tu presupuesto sin perder funcionalidad.", "fas fa-exchange-alt")
            ]
            for titulo, desc, icono in ventajas_defecto:
                db_query("INSERT INTO beneficios (titulo, descripcion, icono) VALUES (%s, %s, %s)", (titulo, desc, icono))

        config_raw = db_query("SELECT clave, valor FROM configuracion", fetch=True) or []
        config = {r[0]: r[1] for r in config_raw}

        servs_raw = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios", fetch=True) or []
        servs = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]} for r in servs_raw]
        
        prods_raw = db_query("SELECT id, nombre, precio, imagen, categoria FROM productos", fetch=True) or []
        prods = [{"id": r[0], "nombre": r[1], "precio": float(r[2]) if r[2] else 0.0, "imagen": r[3], "categoria": r[4]} for r in prods_raw]
        
        parts_raw = db_query("SELECT id, nombre, imagen FROM socios", fetch=True) or []
        parts = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in parts_raw]
        
        reviews_raw = db_query("SELECT id, cliente, puesto, comentario, imagen_cliente, estrellas FROM resenas", fetch=True) or []
        reviews = [{"id": r[0], "cliente": r[1], "puesto": r[2], "comentario": r[3], "imagen_cliente": r[4], "estrellas": r[5]} for r in reviews_raw]
        
        # Mapeo limpio que inyecta correctamente el campo b.icono al HTML
        ben_raw = db_query("SELECT id, icono, titulo, descripcion FROM beneficios ORDER BY id ASC", fetch=True) or []
        beneficios = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in ben_raw]

        obj_raw = db_query("SELECT id, icono, titulo, descripcion FROM clientes_objetivos ORDER BY id ASC", fetch=True) or []
        objetivos = [{"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3]} for r in obj_raw]

        emp_raw = db_query("SELECT id, nombre, imagen FROM empresas_recomiendan ORDER BY id ASC", fetch=True) or []
        empresas = [{"id": r[0], "nombre": r[1], "imagen": r[2]} for r in emp_raw]

        return jsonify({
            "config": config, "servicios": servs, "productos": prods, "socios": parts, "resenas": reviews, "beneficios": beneficios, "objetivos": objetivos, "empresas": empresas
        })
    except Exception as e:
        return jsonify({"error": "Error interno", "detalles": str(e)}), 500

@app.route('/api/servicios/<int:id>', methods=['GET'])
def obtener_servicio_individual(id):
    try:
        res = db_query("SELECT id, icono, titulo, descripcion, imagen, proceso, beneficios FROM servicios WHERE id = %s", (id,), fetch=True)
        if res:
            r = res[0]
            return jsonify({"id": r[0], "icono": r[1], "titulo": r[2], "descripcion": r[3], "imagen": r[4], "proceso": r[5], "beneficios": r[6]})
        return jsonify({"error": "No encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/beneficios', methods=['POST'])
def guardar_beneficio():
    d = request.json or {}
    db_query("INSERT INTO beneficios (icono, titulo, descripcion) VALUES (%s, %s, %s)", (d.get('icono', 'fas fa-check'), d.get('titulo', ''), d.get('descripcion', '')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/beneficios/<int:id>', methods=['PUT'])
def editar_beneficio(id):
    d = request.json or {}
    db_query("UPDATE beneficios SET icono=%s, titulo=%s, descripcion=%s WHERE id=%s", (d.get('icono', 'fas fa-check'), d.get('titulo', ''), d.get('descripcion', ''), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/objetivos', methods=['POST'])
def guardar_objetivo():
    d = request.json or {}
    db_query("INSERT INTO clientes_objetivos (icono, titulo, descripcion) VALUES (%s, %s, %s)", (d.get('icono', 'fas fa-bullseye'), d.get('titulo', ''), d.get('descripcion', '')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/objetivos/<int:id>', methods=['PUT'])
def editar_objetivo(id):
    d = request.json or {}
    db_query("UPDATE clientes_objetivos SET icono=%s, titulo=%s, descripcion=%s WHERE id=%s", (d.get('icono', 'fas fa-bullseye'), d.get('titulo', ''), d.get('descripcion', ''), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/recomiendan', methods=['POST'])
def guardar_empresa():
    d = request.json or {}
    db_query("INSERT INTO empresas_recomiendan (nombre, imagen) VALUES (%s, %s)", (d.get('nombre', 'Empresa'), d.get('imagen', '')))
    return jsonify({"mensaje": "✅"})

@app.route('/api/recomiendan/<int:id>', methods=['PUT'])
def editar_empresa(id):
    d = request.json or {}
    db_query("UPDATE empresas_recomiendan SET nombre=%s, imagen=%s WHERE id=%s", (d.get('nombre', 'Empresa'), d.get('imagen', ''), id))
    return jsonify({"mensaje": "✅"})

@app.route('/api/config', methods=['POST'])
def guardar_config():
    d = request.json or {}
    claves_permitidas = ['hero_titulo', 'mision', 'vision', 'compromiso']
    for k in claves_permitidas:
        if k in d:
            db_query("INSERT INTO configuracion (clave, valor) VALUES (%s, %s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor", (k, d[k]))
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
    db_query("INSERT INTO servicios (icono, titulo, descripcion, imagen, proceso, beneficios) VALUES (%s, %s, %s, %s, %s, %s)", (d.get('icono', '⚙'), d.get('titulo', ''), d.get('descripcion', ''), d.get('imagen', ''), d.get('proceso', ''), d.get('beneficios', '')))
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
    db_query("UPDATE servicios SET icono=%s, titulo=%s, descripcion=%s, imagen=%s, proceso=%s, beneficios=%s WHERE id=%s", (d.get('icono', '⚙'), d.get('titulo', ''), d.get('descripcion', ''), d.get('imagen',''), d.get('proceso', ''), d.get('beneficios', ''), id))
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
    tablas_permitidas = ['productos', 'servicios', 'socios', 'resenas', 'beneficios', 'clientes_objetivos', 'empresas_recomiendan']
    if tabla in tablas_permitidas:
        db_query(f"DELETE FROM {tabla} WHERE id = %s", (id,))
        return jsonify({"mensaje": "🗑️"})
    return jsonify({"error": "No válida"}), 400

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)