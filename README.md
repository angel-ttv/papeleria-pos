# POS Papelería — Punto de venta (rescatado 6 nov 2026)

Sistema de punto de venta para la papelería, en Flask + SQLite.

## Archivos
- `app.py` (337 líneas) — Flask con sesiones y login (`login_required`), rutas de venta/caja.
- `database.py` (308 líneas) — SQLite: usuarios (admin/empleado, contraseñas SHA256), productos (código de barras, precio costo/venta/mayoreo, existencia, stock mínimo), ventas, detalle_ventas, caja_movimientos, configuracion.
- `index-9.html` — "POS Papelería", tema oscuro industrial/neón, escáner de código de barras (html5-qrcode).
- `papeleria.db` — base real: 1 usuario, 8 productos, 0 ventas registradas, 1 movimiento de caja, 4 configuraciones.

## Nota
La base trae 8 productos cargados pero ninguna venta registrada: se instaló y casi no se usó (o se usó en otra copia). No se incluye el `.pyc` (caché compilado, se regenera).
