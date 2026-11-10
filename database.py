import sqlite3
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'papeleria.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL,
            rol TEXT NOT NULL CHECK(rol IN ('admin', 'empleado'))
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            codigo_barras TEXT PRIMARY KEY,
            descripcion TEXT NOT NULL,
            precio_costo REAL NOT NULL DEFAULT 0,
            precio_venta REAL NOT NULL DEFAULT 0,
            precio_mayoreo REAL NOT NULL DEFAULT 0,
            existencia REAL NOT NULL DEFAULT 0,
            stock_minimo REAL NOT NULL DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            total REAL NOT NULL,
            metodo_pago TEXT NOT NULL CHECK(metodo_pago IN ('efectivo','dolar','tarjeta','fiado','mixto')),
            pago_con REAL NOT NULL DEFAULT 0,
            cambio REAL NOT NULL DEFAULT 0,
            usuario_id INTEGER,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS detalle_ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER NOT NULL,
            codigo_barras TEXT NOT NULL,
            cantidad REAL NOT NULL,
            precio_unitario REAL NOT NULL,
            importe REAL NOT NULL,
            FOREIGN KEY(venta_id) REFERENCES ventas(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS caja_movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL CHECK(tipo IN ('apertura','ingreso','egreso','cierre')),
            monto REAL NOT NULL,
            motivo TEXT,
            fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            usuario_id INTEGER,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    ''')

    # Valores por defecto
    c.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('tipo_cambio_dolar', '17.50')")
    c.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('nombre_negocio', 'Mi Papelería')")
    c.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('direccion', 'Dirección del negocio')")
    c.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES ('telefono', '')")

    # Usuario admin por defecto
    c.execute("INSERT OR IGNORE INTO usuarios (usuario, contrasena, rol) VALUES (?, ?, ?)",
              ('admin', hash_password('admin123'), 'admin'))

    # Productos de ejemplo para papelería
    productos_demo = [
        ('7501000000001', 'Cuaderno Profesional 100h', 12.50, 25.00, 22.00, 50, 5),
        ('7501000000002', 'Bolígrafo Azul BIC', 3.00, 6.00, 5.00, 200, 20),
        ('7501000000003', 'Lápiz HB Mongol', 1.50, 3.50, 3.00, 300, 30),
        ('7501000000004', 'Goma de borrar blanca', 2.00, 5.00, 4.00, 150, 15),
        ('7501000000005', 'Tijeras escolares', 15.00, 35.00, 30.00, 40, 5),
        ('7501000000006', 'Regla 30cm transparente', 5.00, 12.00, 10.00, 80, 10),
        ('7501000000007', 'Folder Manila tamaño carta', 2.50, 6.00, 5.00, 100, 10),
        ('7501000000008', 'Cinta adhesiva Scotch', 8.00, 18.00, 15.00, 60, 6),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO productos VALUES (?,?,?,?,?,?,?)",
        productos_demo
    )

    conn.commit()
    conn.close()
    print("[DB] Base de datos inicializada correctamente.")


def get_config(clave):
    conn = get_db()
    row = conn.execute("SELECT valor FROM configuracion WHERE clave=?", (clave,)).fetchone()
    conn.close()
    return row['valor'] if row else None


def set_config(clave, valor):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?,?)", (clave, str(valor)))
    conn.commit()
    conn.close()


def buscar_producto(codigo):
    conn = get_db()
    row = conn.execute("SELECT * FROM productos WHERE codigo_barras=?", (codigo,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def listar_productos(busqueda=''):
    conn = get_db()
    if busqueda:
        rows = conn.execute(
            "SELECT * FROM productos WHERE codigo_barras LIKE ? OR descripcion LIKE ? ORDER BY descripcion",
            (f'%{busqueda}%', f'%{busqueda}%')
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM productos ORDER BY descripcion").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def guardar_producto(data):
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO productos 
        (codigo_barras, descripcion, precio_costo, precio_venta, precio_mayoreo, existencia, stock_minimo)
        VALUES (?,?,?,?,?,?,?)
    ''', (
        data['codigo_barras'], data['descripcion'],
        float(data.get('precio_costo', 0)), float(data.get('precio_venta', 0)),
        float(data.get('precio_mayoreo', 0)), float(data.get('existencia', 0)),
        float(data.get('stock_minimo', 0))
    ))
    conn.commit()
    conn.close()


def ajustar_stock(codigo, cantidad, operacion='sumar'):
    conn = get_db()
    if operacion == 'sumar':
        conn.execute("UPDATE productos SET existencia = existencia + ? WHERE codigo_barras=?", (cantidad, codigo))
    elif operacion == 'restar':
        conn.execute("UPDATE productos SET existencia = existencia - ? WHERE codigo_barras=?", (cantidad, codigo))
    else:
        conn.execute("UPDATE productos SET existencia = ? WHERE codigo_barras=?", (cantidad, codigo))
    conn.commit()
    conn.close()


def registrar_venta(total, metodo_pago, pago_con, cambio, usuario_id, items):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO ventas (total, metodo_pago, pago_con, cambio, usuario_id)
        VALUES (?,?,?,?,?)
    ''', (total, metodo_pago, pago_con, cambio, usuario_id))
    venta_id = cur.lastrowid

    for item in items:
        cur.execute('''
            INSERT INTO detalle_ventas (venta_id, codigo_barras, cantidad, precio_unitario, importe)
            VALUES (?,?,?,?,?)
        ''', (venta_id, item['codigo_barras'], item['cantidad'], item['precio_unitario'], item['importe']))
        # Descontar del inventario
        cur.execute("UPDATE productos SET existencia = existencia - ? WHERE codigo_barras=?",
                    (item['cantidad'], item['codigo_barras']))

    conn.commit()
    conn.close()
    return venta_id


def registrar_movimiento_caja(tipo, monto, motivo, usuario_id):
    conn = get_db()
    conn.execute('''
        INSERT INTO caja_movimientos (tipo, monto, motivo, usuario_id)
        VALUES (?,?,?,?)
    ''', (tipo, monto, motivo, usuario_id))
    conn.commit()
    conn.close()


def calcular_corte_caja():
    conn = get_db()

    apertura = conn.execute('''
        SELECT monto, fecha FROM caja_movimientos 
        WHERE tipo='apertura' ORDER BY id DESC LIMIT 1
    ''').fetchone()

    apertura_monto = apertura['monto'] if apertura else 0
    apertura_fecha = apertura['fecha'] if apertura else 'N/A'

    # Ventas en efectivo y dólar (cuentan como efectivo físico)
    ventas_efectivo = conn.execute('''
        SELECT COALESCE(SUM(total),0) as total FROM ventas 
        WHERE metodo_pago IN ('efectivo','dolar')
        AND fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
    ''').fetchone()['total']

    ventas_tarjeta = conn.execute('''
        SELECT COALESCE(SUM(total),0) as total FROM ventas 
        WHERE metodo_pago='tarjeta'
        AND fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
    ''').fetchone()['total']

    ventas_fiado = conn.execute('''
        SELECT COALESCE(SUM(total),0) as total FROM ventas 
        WHERE metodo_pago='fiado'
        AND fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
    ''').fetchone()['total']

    ventas_mixto = conn.execute('''
        SELECT COALESCE(SUM(total),0) as total FROM ventas 
        WHERE metodo_pago='mixto'
        AND fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
    ''').fetchone()['total']

    total_ventas = conn.execute('''
        SELECT COALESCE(SUM(total),0) as total FROM ventas 
        WHERE fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
    ''').fetchone()['total']

    num_ventas = conn.execute('''
        SELECT COUNT(*) as cnt FROM ventas 
        WHERE fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
    ''').fetchone()['cnt']

    ingresos = conn.execute('''
        SELECT COALESCE(SUM(monto),0) as total FROM caja_movimientos 
        WHERE tipo='ingreso'
        AND fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
    ''').fetchone()['total']

    egresos = conn.execute('''
        SELECT COALESCE(SUM(monto),0) as total FROM caja_movimientos 
        WHERE tipo='egreso'
        AND fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
    ''').fetchone()['total']

    total_esperado = apertura_monto + ventas_efectivo + ingresos - egresos

    # Últimas ventas del turno
    ultimas_ventas = conn.execute('''
        SELECT v.id, v.fecha, v.total, v.metodo_pago, u.usuario
        FROM ventas v LEFT JOIN usuarios u ON v.usuario_id=u.id
        WHERE v.fecha >= (SELECT COALESCE(MAX(fecha),'1900-01-01') FROM caja_movimientos WHERE tipo='apertura')
        ORDER BY v.id DESC LIMIT 20
    ''').fetchall()

    conn.close()
    return {
        'apertura_monto': apertura_monto,
        'apertura_fecha': apertura_fecha,
        'ventas_efectivo': ventas_efectivo,
        'ventas_tarjeta': ventas_tarjeta,
        'ventas_fiado': ventas_fiado,
        'ventas_mixto': ventas_mixto,
        'total_ventas': total_ventas,
        'num_ventas': num_ventas,
        'ingresos': ingresos,
        'egresos': egresos,
        'total_esperado': total_esperado,
        'ultimas_ventas': [dict(r) for r in ultimas_ventas]
    }


def autenticar_usuario(usuario, contrasena):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM usuarios WHERE usuario=? AND contrasena=?",
        (usuario, hash_password(contrasena))
    ).fetchone()
    conn.close()
    return dict(row) if row else None


if __name__ == '__main__':
    init_db()