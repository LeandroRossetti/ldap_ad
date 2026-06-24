import io
import csv
import os
import sqlite3
from functools import wraps
from datetime import datetime, time

from flask import Flask, request, render_template, redirect, url_for, session, flash, Response
from ldap3 import Server, Connection, SUBTREE
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

AD_SERVER = os.getenv('AD_SERVER')
AD_PORT = int(os.getenv('AD_PORT'))
AD_DOMAIN = os.getenv('AD_DOMAIN')
AD_BASE_DN = os.getenv('AD_BASE_DN')
HORA_INICIO = int(os.getenv('HORA_INICIO'))
HORA_FIN = int(os.getenv('HORA_FIN'))
DATABASE_PATH = os.getenv('DATABASE_PATH')

AD_GRUPO_ADMIN = [g.strip().lower() for g in os.getenv('AD_GRUPO_ADMIN', 'Admin').split(',') if g.strip()]
AD_GRUPO_OPERADOR = [g.strip().lower() for g in os.getenv('AD_GRUPO_OPERADOR', 'Operador').split(',') if g.strip()]
AD_GRUPO_CONSULTA = [g.strip().lower() for g in os.getenv('AD_GRUPO_CONSULTA', 'Consulta').split(',') if g.strip()]

REQUIRED_ENV_VARS = {
    'SECRET_KEY': 'Clave secreta para sesiones Flask',
    'AD_SERVER': 'IP del servidor Active Directory',
    'AD_PORT': 'Puerto del servidor AD (ej: 389)',
    'AD_DOMAIN': 'Nombre del dominio AD (ej: IFTS)',
    'AD_BASE_DN': 'Base DN del AD (ej: dc=IFTS,dc=local)',
    'HORA_INICIO': 'Hora de inicio del horario laboral (ej: 8)',
    'HORA_FIN': 'Hora de fin del horario laboral (ej: 18)',
    'DATABASE_PATH': 'Ruta al archivo de base de datos (ej: stock.db)',
}

missing = [f'{k} -> {v}' for k, v in REQUIRED_ENV_VARS.items() if os.getenv(k) is None]
if missing:
    print('ERROR: Faltan variables de entorno obligatorias en .env:')
    for m in missing:
        print(f'  - {m}')
    print('Copiá .env.example a .env y completá los valores.')
    exit(1)


def mapear_roles(grupos_ad):
    roles = []
    grupos_lower = [g.lower() for g in grupos_ad]
    if any(g in grupos_lower for g in AD_GRUPO_ADMIN):
        roles.append('Admin')
    if any(g in grupos_lower for g in AD_GRUPO_OPERADOR):
        roles.append('Operador')
    if any(g in grupos_lower for g in AD_GRUPO_CONSULTA):
        roles.append('Consulta')
    return roles


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                stock_actual INTEGER NOT NULL DEFAULT 0,
                stock_minimo INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('entrada','salida')),
                cantidad INTEGER NOT NULL CHECK(cantidad > 0),
                stock_resultante INTEGER NOT NULL,
                usuario TEXT NOT NULL,
                observacion TEXT DEFAULT '',
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            );
        ''')


init_db()


def validar_horario():
    hora_actual = datetime.now().time()
    return time(HORA_INICIO, 0) <= hora_actual <= time(HORA_FIN, 0)


def autenticar_ad(usuario, password):
    server = Server(AD_SERVER, port=AD_PORT)
    usuario_ad = f'{AD_DOMAIN}\\{usuario}'
    usuario_ad = f'{usuario}@{AD_DOMAIN}.local'
    conn = Connection(server, user=usuario_ad, password=password, auto_bind=False)
    if not conn.bind():
        return None

    filtro = f'(sAMAccountName={usuario})'
    conn.search(AD_BASE_DN, filtro, search_scope=SUBTREE, attributes=['memberOf'])

    grupos = []
    if conn.entries and 'memberOf' in conn.entries[0]:
        member_of = conn.entries[0].memberOf.values
        grupos = [g.split(',')[0].replace('CN=', '') for g in member_of]

    conn.unbind()
    return grupos


def requiere_rol(rol_requerido):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'usuario' not in session:
                return redirect(url_for('login'))
            if rol_requerido not in session.get('grupos', []) and 'Admin' not in session.get('grupos', []):
                flash('No tenés permisos para acceder a esta sección.')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if not validar_horario():
            flash('El sistema solo está disponible de {} a {} hs.'.format(HORA_INICIO, HORA_FIN))
            return render_template('login.html')

        usuario = request.form['usuario']
        password = request.form['password']

        grupos = autenticar_ad(usuario, password)

        if grupos is not None:
            session['usuario'] = usuario
            session['grupos'] = mapear_roles(grupos)
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', usuario=session['usuario'], grupos=session['grupos'])


@app.route('/productos')
def listar_productos():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    with get_db() as db:
        productos = db.execute('SELECT * FROM productos ORDER BY nombre').fetchall()
    return render_template('productos.html', productos=productos)


@app.route('/productos/nuevo', methods=['GET', 'POST'])
@requiere_rol('Admin')
def nuevo_producto():
    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form.get('descripcion', '')
        stock_minimo = int(request.form.get('stock_minimo', 0))
        with get_db() as db:
            db.execute(
                'INSERT INTO productos (nombre, descripcion, stock_actual, stock_minimo) VALUES (?, ?, 0, ?)',
                (nombre, descripcion, stock_minimo)
            )
        flash('Producto creado correctamente.')
        return redirect(url_for('listar_productos'))
    return render_template('producto_form.html', producto=None)


@app.route('/productos/<int:id>/editar', methods=['GET', 'POST'])
@requiere_rol('Admin')
def editar_producto(id):
    with get_db() as db:
        producto = db.execute('SELECT * FROM productos WHERE id = ?', (id,)).fetchone()
    if not producto:
        flash('Producto no encontrado.')
        return redirect(url_for('listar_productos'))

    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form.get('descripcion', '')
        stock_minimo = int(request.form.get('stock_minimo', 0))
        with get_db() as db:
            db.execute(
                'UPDATE productos SET nombre = ?, descripcion = ?, stock_minimo = ? WHERE id = ?',
                (nombre, descripcion, stock_minimo, id)
            )
        flash('Producto actualizado correctamente.')
        return redirect(url_for('listar_productos'))
    return render_template('producto_form.html', producto=producto)


@app.route('/productos/<int:id>/eliminar', methods=['POST'])
@requiere_rol('Admin')
def eliminar_producto(id):
    with get_db() as db:
        db.execute('DELETE FROM movimientos WHERE producto_id = ?', (id,))
        db.execute('DELETE FROM productos WHERE id = ?', (id,))
    flash('Producto eliminado.')
    return redirect(url_for('listar_productos'))


@app.route('/movimientos')
def listar_movimientos():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    with get_db() as db:
        movimientos = db.execute('''
            SELECT m.*, p.nombre AS producto_nombre
            FROM movimientos m
            JOIN productos p ON p.id = m.producto_id
            ORDER BY m.fecha DESC
        ''').fetchall()
    return render_template('movimientos.html', movimientos=movimientos)


@app.route('/movimientos/nuevo', methods=['GET', 'POST'])
@requiere_rol('Operador')
def nuevo_movimiento():
    with get_db() as db:
        productos = db.execute('SELECT * FROM productos ORDER BY nombre').fetchall()

    if request.method == 'POST':
        producto_id = int(request.form['producto_id'])
        tipo = request.form['tipo']
        cantidad = int(request.form['cantidad'])
        observacion = request.form.get('observacion', '')
        usuario = session['usuario']

        with get_db() as db:
            producto = db.execute('SELECT * FROM productos WHERE id = ?', (producto_id,)).fetchone()
            if not producto:
                flash('Producto no encontrado.')
                return redirect(url_for('nuevo_movimiento'))

            if tipo == 'salida' and producto['stock_actual'] < cantidad:
                flash('Stock insuficiente para realizar la salida.')
                return redirect(url_for('nuevo_movimiento'))

            stock_resultante = producto['stock_actual'] + cantidad if tipo == 'entrada' else producto['stock_actual'] - cantidad

            db.execute(
                'INSERT INTO movimientos (producto_id, tipo, cantidad, stock_resultante, usuario, observacion) VALUES (?, ?, ?, ?, ?, ?)',
                (producto_id, tipo, cantidad, stock_resultante, usuario, observacion)
            )
            db.execute(
                'UPDATE productos SET stock_actual = ? WHERE id = ?',
                (stock_resultante, producto_id)
            )

        flash('Movimiento registrado correctamente.')
        return redirect(url_for('listar_movimientos'))

    return render_template('movimiento_form.html', productos=productos)


@app.route('/reportes')
@requiere_rol('Consulta')
def reportes():
    with get_db() as db:
        productos = db.execute('SELECT * FROM productos ORDER BY nombre').fetchall()
        movimientos_recientes = db.execute('''
            SELECT m.*, p.nombre AS producto_nombre
            FROM movimientos m
            JOIN productos p ON p.id = m.producto_id
            ORDER BY m.fecha DESC LIMIT 20
        ''').fetchall()
    return render_template('reportes.html', productos=productos, movimientos_recientes=movimientos_recientes)


@app.route('/exportar/stock')
@requiere_rol('Consulta')
def exportar_stock_csv():
    with get_db() as db:
        productos = db.execute('SELECT * FROM productos ORDER BY nombre').fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Nombre', 'Descripcion', 'Stock Actual', 'Stock Minimo'])
    for p in productos:
        writer.writerow([p['id'], p['nombre'], p['descripcion'], p['stock_actual'], p['stock_minimo']])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=reporte_stock.csv'}
    )


@app.route('/exportar/movimientos')
@requiere_rol('Consulta')
def exportar_movimientos_csv():
    with get_db() as db:
        movimientos = db.execute('''
            SELECT m.*, p.nombre AS producto_nombre
            FROM movimientos m
            JOIN productos p ON p.id = m.producto_id
            ORDER BY m.fecha DESC
        ''').fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Fecha', 'Producto', 'Tipo', 'Cantidad', 'Stock Resultante', 'Usuario', 'Observacion'])
    for m in movimientos:
        writer.writerow([m['id'], m['fecha'], m['producto_nombre'], m['tipo'], m['cantidad'], m['stock_resultante'], m['usuario'], m['observacion']])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=reporte_movimientos.csv'}
    )


if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true', port=int(os.getenv('FLASK_PORT', 5000)))
