try:
    from flask import Flask, request, jsonify, render_template, session
except ImportError as exc:
    raise ImportError("Flask no está instalado. Ejecuta 'pip install flask' para continuar.") from exc
from functools import wraps
import os
import sys

# Asegura que database.py esté en el path
sys.path.insert(0, os.path.dirname(__file__))
import database as db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'papeleria-pos-secret-2024')

# ─── Inicializar DB al arrancar ───────────────────────────────────────────────
db.init_db()


# ─── Decorador de autenticación ───────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return jsonify({'error': 'No autenticado'}), 401
        return f(*args, **kwargs)
    return decorated


# ─── RUTAS PRINCIPALES ────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


# ─── AUTH ─────────────────────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    usuario = db.autenticar_usuario(data.get('usuario', ''), data.get('contrasena', ''))
    if usuario:
        session['usuario_id'] = usuario['id']
        session['usuario_nombre'] = usuario['usuario']
        session['usuario_rol'] = usuario['rol']
        return jsonify({'ok': True, 'usuario': usuario['usuario'], 'rol': usuario['rol']})
    return jsonify({'ok': False, 'error': 'Credenciales incorrectas'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/sesion', methods=['GET'])
def get_sesion():
    if 'usuario_id' in session:
        return jsonify({
            'autenticado': True,
            'usuario': session.get('usuario_nombre'),
            'rol': session.get('usuario_rol')
        })
    return jsonify({'autenticado': False})


# ─── PRODUCTOS ────────────────────────────────────────────────────────────────
@app.route('/api/producto/<codigo>', methods=['GET'])
def get_producto(codigo):
    producto = db.buscar_producto(codigo.strip())
    if producto:
        return jsonify(producto)
    return jsonify({'error': 'Producto no encontrado', 'codigo': codigo}), 404


@app.route('/api/productos', methods=['GET'])
def get_productos():
    busqueda = request.args.get('q', '')
    return jsonify(db.listar_productos(busqueda))


@app.route('/api/producto', methods=['POST'])
@login_required
def crear_producto():
    data = request.get_json()
    if not data.get('codigo_barras') or not data.get('descripcion'):
        return jsonify({'error': 'Código y descripción son requeridos'}), 400
    try:
        db.guardar_producto(data)
        return jsonify({'ok': True, 'mensaje': 'Producto guardado correctamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/producto/<codigo>', methods=['PUT'])
@login_required
def actualizar_producto(codigo):
    data = request.get_json()
    data['codigo_barras'] = codigo
    try:
        db.guardar_producto(data)
        return jsonify({'ok': True, 'mensaje': 'Producto actualizado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/producto/<codigo>', methods=['DELETE'])
@login_required
def eliminar_producto(codigo):
    conn = db.get_db()
    conn.execute("DELETE FROM productos WHERE codigo_barras=?", (codigo,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/inventario/ajuste', methods=['POST'])
@login_required
def ajuste_inventario():
    data = request.get_json()
    codigo = data.get('codigo_barras', '').strip()
    cantidad = float(data.get('cantidad', 0))
    operacion = data.get('operacion', 'sumar')  # sumar, restar, establecer

    producto = db.buscar_producto(codigo)
    if not producto:
        return jsonify({'error': 'Producto no encontrado'}), 404

    db.ajustar_stock(codigo, cantidad, operacion)
    producto_actualizado = db.buscar_producto(codigo)
    return jsonify({'ok': True, 'producto': producto_actualizado})


# ─── VENTAS ───────────────────────────────────────────────────────────────────
@app.route('/api/venta', methods=['POST'])
@login_required
def registrar_venta():
    data = request.get_json()
    items = data.get('items', [])
    metodo_pago = data.get('metodo_pago', 'efectivo')
    pago_con = float(data.get('pago_con', 0))
    usuario_id = session.get('usuario_id')

    if not items:
        return jsonify({'error': 'No hay artículos en la venta'}), 400

    # Calcular total y validar stock
    total = 0
    items_procesados = []
    for item in items:
        codigo = item.get('codigo_barras', '').strip()
        cantidad = float(item.get('cantidad', 1))
        producto = db.buscar_producto(codigo)

        if not producto:
            return jsonify({'error': f'Producto {codigo} no encontrado'}), 404

        if producto['existencia'] < cantidad and metodo_pago != 'fiado':
            return jsonify({
                'error': f'Stock insuficiente para {producto["descripcion"]}. '
                         f'Disponible: {producto["existencia"]}'
            }), 400

        precio_unitario = float(item.get('precio_unitario', producto['precio_venta']))
        importe = round(precio_unitario * cantidad, 2)
        total += importe
        items_procesados.append({
            'codigo_barras': codigo,
            'cantidad': cantidad,
            'precio_unitario': precio_unitario,
            'importe': importe,
            'descripcion': producto['descripcion']
        })

    total = round(total, 2)

    # Calcular cambio
    if metodo_pago in ('efectivo', 'dolar'):
        cambio = round(pago_con - total, 2) if pago_con > 0 else 0
    elif metodo_pago == 'mixto':
        efectivo_entregado = float(data.get('efectivo_mixto', 0))
        cambio = round(max(0, efectivo_entregado - (total - float(data.get('tarjeta_mixto', 0)) - float(data.get('otros_mixto', 0)))), 2)
    else:
        cambio = 0

    venta_id = db.registrar_venta(total, metodo_pago, pago_con, cambio, usuario_id, items_procesados)

    return jsonify({
        'ok': True,
        'venta_id': venta_id,
        'total': total,
        'cambio': cambio,
        'items': items_procesados
    })


@app.route('/api/ventas/recientes', methods=['GET'])
@login_required
def ventas_recientes():
    conn = db.get_db()
    rows = conn.execute('''
        SELECT v.id, v.fecha, v.total, v.metodo_pago, v.cambio, u.usuario
        FROM ventas v LEFT JOIN usuarios u ON v.usuario_id=u.id
        ORDER BY v.id DESC LIMIT 50
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/venta/<int:venta_id>', methods=['GET'])
@login_required
def get_venta(venta_id):
    conn = db.get_db()
    venta = conn.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
    if not venta:
        conn.close()
        return jsonify({'error': 'Venta no encontrada'}), 404
    detalles = conn.execute('''
        SELECT d.*, p.descripcion FROM detalle_ventas d
        LEFT JOIN productos p ON d.codigo_barras=p.codigo_barras
        WHERE d.venta_id=?
    ''', (venta_id,)).fetchall()
    conn.close()
    return jsonify({'venta': dict(venta), 'detalles': [dict(d) for d in detalles]})


# ─── CAJA ─────────────────────────────────────────────────────────────────────
@app.route('/api/caja/movimiento', methods=['POST'])
@login_required
def movimiento_caja():
    data = request.get_json()
    tipo = data.get('tipo')
    monto = float(data.get('monto', 0))
    motivo = data.get('motivo', '')
    usuario_id = session.get('usuario_id')

    if tipo not in ('apertura', 'ingreso', 'egreso', 'cierre'):
        return jsonify({'error': 'Tipo de movimiento inválido'}), 400
    if monto < 0:
        return jsonify({'error': 'El monto no puede ser negativo'}), 400

    db.registrar_movimiento_caja(tipo, monto, motivo, usuario_id)
    return jsonify({'ok': True, 'mensaje': f'Movimiento de {tipo} registrado: ${monto:.2f}'})


@app.route('/api/caja/corte', methods=['GET'])
@login_required
def corte_caja():
    corte = db.calcular_corte_caja()
    return jsonify(corte)


@app.route('/api/caja/movimientos', methods=['GET'])
@login_required
def listar_movimientos():
    conn = db.get_db()
    rows = conn.execute('''
        SELECT cm.*, u.usuario FROM caja_movimientos cm
        LEFT JOIN usuarios u ON cm.usuario_id=u.id
        ORDER BY cm.id DESC LIMIT 100
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
@app.route('/api/config/dolar', methods=['GET'])
def get_dolar():
    valor = db.get_config('tipo_cambio_dolar')
    return jsonify({'tipo_cambio_dolar': float(valor) if valor else 17.50})


@app.route('/api/config/dolar', methods=['POST'])
@login_required
def set_dolar():
    data = request.get_json()
    valor = float(data.get('tipo_cambio_dolar', 17.50))
    if valor <= 0:
        return jsonify({'error': 'El tipo de cambio debe ser mayor a 0'}), 400
    db.set_config('tipo_cambio_dolar', valor)
    return jsonify({'ok': True, 'tipo_cambio_dolar': valor})


@app.route('/api/config', methods=['GET'])
def get_config_all():
    conn = db.get_db()
    rows = conn.execute("SELECT clave, valor FROM configuracion").fetchall()
    conn.close()
    return jsonify({r['clave']: r['valor'] for r in rows})


@app.route('/api/config', methods=['POST'])
@login_required
def set_config():
    data = request.get_json()
    for clave, valor in data.items():
        db.set_config(clave, valor)
    return jsonify({'ok': True})


# ─── USUARIOS ─────────────────────────────────────────────────────────────────
@app.route('/api/usuarios', methods=['GET'])
@login_required
def listar_usuarios():
    if session.get('usuario_rol') != 'admin':
        return jsonify({'error': 'Sin permisos'}), 403
    conn = db.get_db()
    rows = conn.execute("SELECT id, usuario, rol FROM usuarios").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/usuario', methods=['POST'])
@login_required
def crear_usuario():
    if session.get('usuario_rol') != 'admin':
        return jsonify({'error': 'Sin permisos'}), 403
    data = request.get_json()
    try:
        conn = db.get_db()
        conn.execute(
            "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (?,?,?)",
            (data['usuario'], db.hash_password(data['contrasena']), data.get('rol', 'empleado'))
        )
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ─── ARRANQUE ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("╔══════════════════════════════════════╗")
    print("║   POS Papelería - Iniciando...       ║")
    print("║   http://0.0.0.0:5000                ║")
    print("║   Usuario: admin / Clave: admin123   ║")
    print("╚══════════════════════════════════════╝")
    app.run(host='0.0.0.0', port=5000, debug=False)