# -*- coding: utf-8 -*-
"""
Esta es una aplicación Flask que sirve como backend para una aplicación de escaneo NFC.
Proporciona una interfaz web para la gestión de usuarios y un panel de control en tiempo real,
así como una API RESTful para recibir y procesar lecturas NFC desde una aplicación móvil.
También incluye autenticación de usuarios y manejo de sesiones.
"""
from werkzeug.security import generate_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from datetime import datetime
import json
import os
import sqlite3
# CORRECCIÓN: Asegúrate de que el nombre del archivo de autenticación sea el correcto.
from autentificacion import validar_credenciales, iniciar_sesion, cerrar_sesion, verificar_sesion, obtener_permisos_usuario, obtener_roles_modulos, obtener_rutas_modulos
from db import obtener_conexion
from pathlib import Path
import unicodedata

# ============================================================================
# CONFIGURACIÓN DE LA APLICACIÓN
# ============================================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'nfc-reader-secret-key-dev-only')
CORS(app, origins=["http://localhost:8100", "http://localhost:4200", "capacitor://localhost", "ionic://localhost", "http://localhost"])
socketio = SocketIO(app, cors_allowed_origins="*")

DATABASE_FILE = 'nfc_readings.db'
APK_FILE = 'static/NFC_Reader.apk'
APK_EXISTS = os.path.exists(APK_FILE)

# ============================================================================
# CLASE DE BASE DE DATOS (NFC Readings)
# ============================================================================
class NFCDatabase:
    """Manejo de base de datos SQLite para lecturas NFC"""
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS nfc_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, device_info TEXT, nfc_data TEXT,
                    timestamp TEXT, formatted_time TEXT, ip_address TEXT, user_agent TEXT
                )''')
    
    def save_reading(self, device_info, nfc_data, ip_address, user_agent):
        timestamp = datetime.now().isoformat()
        formatted_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO nfc_readings (device_info, nfc_data, timestamp, formatted_time, ip_address, user_agent) VALUES (?, ?, ?, ?, ?, ?)',
                           (json.dumps(device_info), json.dumps(nfc_data), timestamp, formatted_time, ip_address, user_agent))
            reading_id = cursor.lastrowid
        return {'id': reading_id, 'device_info': device_info, 'nfc_data': nfc_data, 'timestamp': timestamp, 'formatted_time': formatted_time, 'ip_address': ip_address}
    
    def get_all_readings(self, limit=100):
        with sqlite3.connect(DATABASE_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM nfc_readings ORDER BY timestamp DESC LIMIT ?', (limit,))
            return [{k: (json.loads(row[k]) if k in ['device_info', 'nfc_data'] else row[k]) for k in row.keys()} for row in cursor.fetchall()]
    
    def get_stats(self):
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            total_readings = cursor.execute('SELECT COUNT(*) FROM nfc_readings').fetchone()[0]
            unique_devices = cursor.execute('SELECT COUNT(DISTINCT ip_address) FROM nfc_readings').fetchone()[0]
            last_reading = cursor.execute('SELECT formatted_time FROM nfc_readings ORDER BY timestamp DESC LIMIT 1').fetchone()
            return {'total_readings': total_readings, 'unique_devices': unique_devices, 'last_reading_time': last_reading[0] if last_reading else 'Ninguna'}

db = NFCDatabase()

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================
def _slugify(texto: str) -> str:
    if not texto: return ''
    texto = unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('utf-8')
    return ''.join(ch for ch in texto.lower() if ch.isalnum())

def generar_nombre_usuario(primer_nombre: str, apellido_pat: str, apellido_mat: str) -> str:
    pn, ap, am = _slugify(primer_nombre), _slugify(apellido_pat), _slugify(apellido_mat)
    return f"{pn[0] if pn else ''}{ap}{am[0] if am else ''}"

# ============================================================================
# INICIALIZACIÓN DE LA BASE DE DATOS DE INVENTARIO
# ============================================================================
def init_inventory_db():
    """
    Verifica las tablas de inventario. No crea tablas que ya existen.
    Asegura que la tabla 'tipos_movimiento' tenga datos básicos si está vacía.
    """
    with obtener_conexion() as conn:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS tipos_movimiento (tipo_movimiento_id INTEGER PRIMARY KEY, nombre TEXT NOT NULL UNIQUE)")
        
        if cur.execute("SELECT COUNT(*) FROM tipos_movimiento").fetchone()[0] == 0:
            print("INFO: Poblando la tabla 'tipos_movimiento' con valores por defecto.")
            try:
                cur.executemany("INSERT INTO tipos_movimiento (tipo_movimiento_id, nombre) VALUES (?, ?)", [
                    (1, 'Asignación'), (2, 'Devolución'), (3, 'Baja'), (4, 'Préstamo')
                ])
                conn.commit()
            except sqlite3.IntegrityError:
                pass
        
        print("INFO: Base de datos de inventario verificada.")


# ============================================================================
# RUTAS WEB - AUTENTICACIÓN Y DASHBOARD
# ============================================================================
@app.route('/', methods=['GET', 'POST'])
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if verificar_sesion():
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        datos_usuario = validar_credenciales(request.form.get('username'), request.form.get('password'))
        if datos_usuario:
            iniciar_sesion(datos_usuario)
            return redirect(url_for('dashboard'))
        else:
            flash('Credenciales incorrectas.', 'danger')
    return render_template('login.html', apk_exists=APK_EXISTS)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    cerrar_sesion()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not verificar_sesion():
        return redirect(url_for('login'))
    permiso = obtener_permisos_usuario()
    roles_modulos = obtener_roles_modulos()
    rutas = obtener_rutas_modulos()
    
    botones = []
    for texto, roles_permitidos in roles_modulos.items():
        habilitado = permiso in roles_permitidos
        botones.append({
            'texto': texto,
            'habilitado': habilitado,
            'url': url_for(rutas.get(texto, 'dashboard')) 
        })

    return render_template('dashboard.html', usuario=session.get('nombre'), permiso=permiso, fecha=datetime.now().strftime('%d/%m/%Y %H:%M'), botones=botones)


# ============================================================================
# RUTAS WEB - GESTIÓN DE USUARIOS
# ============================================================================
def _crear_nuevo_usuario_db(form_data):
    """Lógica de negocio para crear un nuevo usuario y su persona asociada."""
    rut = (form_data.get('rut') or '').strip()
    dv = (form_data.get('dv') or '').strip()
    primer_nombre = (form_data.get('primer_nombre') or '').strip()
    apellido_pat = (form_data.get('apellido_pat') or '').strip()
    nombre_usuario = (form_data.get('nombre_usuario') or '').strip()
    password = form_data.get('password') or ''
    password2 = form_data.get('password2') or ''

    if not all([rut, dv, primer_nombre, apellido_pat]):
        return False, 'RUT, DV, Primer nombre y Apellido paterno son obligatorios.'
    if not nombre_usuario:
        nombre_usuario = generar_nombre_usuario(primer_nombre, form_data.get('apellido_pat'), form_data.get('apellido_mat'))
    if not password or password != password2:
        return False, 'Las contraseñas son obligatorias y deben coincidir.'

    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            if cur.execute('SELECT 1 FROM usuarios WHERE nombre_usuario = ?', (nombre_usuario,)).fetchone():
                return False, 'El nombre de usuario ya existe.'
            
            if not cur.execute('SELECT 1 FROM personas WHERE rut = ?', (rut,)).fetchone():
                cur.execute('INSERT INTO personas (rut, dv, primer_nombre, segundo_nombre, apellido_pat, apellido_mat, telefono, correo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                            (rut, dv, primer_nombre, form_data.get('segundo_nombre'), form_data.get('apellido_pat'), form_data.get('apellido_mat'), form_data.get('telefono'), form_data.get('correo')))

            password_hash = generate_password_hash(password)
            rol_result = cur.execute('SELECT id_rol FROM roles WHERE nombre_rol = ?', (form_data.get('rol'),)).fetchone()
            id_rol_val = rol_result[0] if rol_result else None

            cur.execute('INSERT INTO usuarios (nombre_usuario, password, id_rol, activo, persona_rut, area_id, modulo_venta_id, fecha_creacion) VALUES (?, ?, ?, ?, ?, ?, ?, datetime("now"))',
                        (nombre_usuario, password_hash, id_rol_val, form_data.get('activo', 'Activo'), rut, form_data.get('area_id'), form_data.get('modulo_venta_id')))
            conn.commit()
        return True, 'Usuario creado exitosamente.'
    except Exception as e:
        return False, f'Error de base de datos: {e}'

@app.route('/usuarios/nuevo', methods=['GET', 'POST'])
def crear_usuario():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        exito, mensaje = _crear_nuevo_usuario_db(request.form)
        flash(mensaje, 'success' if exito else 'danger')
        return redirect(url_for('lista_usuarios') if exito else url_for('crear_usuario'))

    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        areas = cur.execute('SELECT area_id, nombre_area AS nombre FROM areas ORDER BY nombre_area').fetchall()
        modulos = cur.execute('SELECT modulo_id, nombre FROM modulos_venta ORDER BY nombre').fetchall()
        roles = [row['nombre_rol'] for row in cur.execute('SELECT nombre_rol FROM roles ORDER BY nombre_rol').fetchall()]

    return render_template('crear_usuario.html', areas=areas, modulos=modulos, roles=roles, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))


@app.route('/usuarios')
def lista_usuarios():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT u.nombre_usuario, p.primer_nombre || ' ' || p.apellido_pat AS nombre_completo, r.nombre_rol, u.activo
            FROM usuarios u JOIN personas p ON u.persona_rut = p.rut LEFT JOIN roles r ON u.id_rol = r.id_rol
            ORDER BY p.primer_nombre
        """)
        usuarios = cur.fetchall()

    return render_template('lista_usuarios.html', usuarios=usuarios, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

def _actualizar_usuario_db(nombre_usuario, form_data):
    """Lógica de negocio para actualizar un usuario."""
    password = form_data.get('password')
    password2 = form_data.get('password2')
    if password and password != password2:
        return False, 'Las contraseñas no coinciden.'

    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            rol_result = cur.execute('SELECT id_rol FROM roles WHERE nombre_rol = ?', (form_data.get('rol'),)).fetchone()
            id_rol_val = rol_result[0] if rol_result else None

            if password:
                password_hash = generate_password_hash(password)
                cur.execute('UPDATE usuarios SET password = ?, id_rol = ?, activo = ?, area_id = ?, modulo_venta_id = ? WHERE nombre_usuario = ?',
                            (password_hash, id_rol_val, form_data.get('activo'), form_data.get('area_id'), form_data.get('modulo_venta_id'), nombre_usuario))
            else:
                cur.execute('UPDATE usuarios SET id_rol = ?, activo = ?, area_id = ?, modulo_venta_id = ? WHERE nombre_usuario = ?',
                            (id_rol_val, form_data.get('activo'), form_data.get('area_id'), form_data.get('modulo_venta_id'), nombre_usuario))
            conn.commit()
        return True, 'Usuario actualizado exitosamente.'
    except Exception as e:
        return False, f'Error de base de datos: {e}'

@app.route('/usuarios/editar/<nombre_usuario>', methods=['GET', 'POST'])
def editar_usuario(nombre_usuario):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        exito, mensaje = _actualizar_usuario_db(nombre_usuario, request.form)
        flash(mensaje, 'success' if exito else 'danger')
        return redirect(url_for('lista_usuarios'))

    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        usuario_data = cur.execute("SELECT u.*, p.*, r.nombre_rol FROM usuarios u JOIN personas p ON u.persona_rut = p.rut LEFT JOIN roles r ON u.id_rol = r.id_rol WHERE u.nombre_usuario = ?", (nombre_usuario,)).fetchone()
        
        if not usuario_data:
            flash('Usuario no encontrado.', 'danger')
            return redirect(url_for('lista_usuarios'))
        
        areas = cur.execute('SELECT area_id, nombre_area AS nombre FROM areas ORDER BY nombre_area').fetchall()
        modulos = cur.execute('SELECT modulo_id, nombre FROM modulos_venta ORDER BY nombre').fetchall()
        roles = [row['nombre_rol'] for row in cur.execute('SELECT nombre_rol FROM roles ORDER BY nombre_rol').fetchall()]

    return render_template('editar_usuario.html', usuario_data=usuario_data, areas=areas, modulos=modulos, roles=roles, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/areas/nuevo', methods=['GET', 'POST'])
def crear_areas():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        if not nombre:
            flash('El nombre del área es obligatorio.', 'warning')
            return redirect(url_for('crear_areas'))
        
        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute('INSERT INTO areas (nombre_area) VALUES (?)', (nombre,))
            flash('Área creada exitosamente.', 'success')
            return redirect(url_for('dashboard'))
        except sqlite3.IntegrityError:
            flash('Esa área ya existe.', 'danger')
        except Exception as e:
            flash(f'Error al crear el área: {e}', 'danger')
        return redirect(url_for('crear_areas'))
        
    return render_template(
        'crear_areas.html',
        usuario=session.get('nombre'),
        permiso=session.get('permiso'),
        fecha=datetime.now().strftime('%d/%m/%Y %H:%M')
    )

@app.route('/roles/nuevo', methods=['GET', 'POST'])
def crear_roles():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        if not nombre:
            flash('El nombre del rol es obligatorio.', 'warning')
            return redirect(url_for('crear_roles'))

        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute('INSERT INTO roles (nombre_rol) VALUES (?)', (nombre,))
            flash('Rol creado exitosamente.', 'success')
            return redirect(url_for('dashboard'))
        except sqlite3.IntegrityError:
            flash('Ese rol ya existe.', 'danger')
        except Exception as e:
            flash(f'Error al crear el rol: {e}', 'danger')
        return redirect(url_for('crear_roles'))

    return render_template(
        'crear_roles.html',
        usuario=session.get('nombre'),
        permiso=session.get('permiso'),
        fecha=datetime.now().strftime('%d/%m/%Y %H:%M')
    )
# ============================================================================
# RUTAS - GESTIÓN TIPO DE PRODUCTOS
# ============================================================================
@app.route('/tipo_producto/nuevo', methods=['GET', 'POST'])
def crear_tipo_producto():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nombre = (request.form.get('nombre_producto') or '').strip()
        print (nombre)
        if not nombre:
            flash('El nombre del tipo de producto es obligatorio.', 'warning')
            return redirect(url_for('crear_tipo_producto'))
        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute('INSERT INTO tipos_producto (tipo_producto) VALUES (?)', (nombre,))
            flash('Tipo de producto creada exitosamente.', 'success')
            return redirect(url_for('dashboard'))
        except sqlite3.IntegrityError:
            flash('Ese tipo de producto ya existe.', 'danger')
        except Exception as e:
            flash(f'Error al crear el tipo de producto: {e}', 'danger')
        return redirect(url_for('crear_tipo_producto'))
        
    return render_template(
        'crear_tipo_producto.html',
        usuario=session.get('nombre'),
        permiso=session.get('permiso'),
        fecha=datetime.now().strftime('%d/%m/%Y %H:%M')
    )

# ============================================================================
# RUTAS - GESTIÓN DE PRODUCTOS
# ============================================================================
@app.route('/productos')
def lista_productos():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                p.producto_id,
                p.nombre,
                tp.tipo_producto as tipo_producto,
                p.numero_serie,
                p.stock_actual,
                ee.nombre as estado_equipo
            FROM productos p
            LEFT JOIN tipos_producto tp ON p.tipo_producto_id = tp.tipo_producto_id
            LEFT JOIN estados_equipo ee ON p.estado_equipo_id = ee.estado_equipo_id
            ORDER BY p.nombre
        """)
        productos = cur.fetchall()

    return render_template(
        'lista_productos.html',
        productos=productos,
        usuario=session.get('nombre'),
        permiso=session.get('permiso'),
        fecha=datetime.now().strftime('%d/%m/%Y %H:%M')
    )

@app.route('/productos/nuevo', methods=['GET', 'POST'])
def crear_producto():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO productos (
                        nombre, tipo_producto_id, numero_serie, numero_factura, 
                        fecha_compra, valor_unitario, proveedor_id, garantia_hasta, 
                        estado_equipo_id, ubicacion_fisica, stock_actual, activo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    request.form['nombre'], request.form['tipo_producto_id'],
                    request.form['numero_serie'], request.form['numero_factura'],
                    request.form['fecha_compra'], request.form['valor_unitario'],
                    request.form.get('proveedor_id'), request.form.get('garantia_hasta'),
                    request.form['estado_equipo_id'], request.form.get('ubicacion_fisica'),
                    request.form.get('stock_actual', 1), 'Activo'
                ))
                conn.commit()
            flash('Producto creado exitosamente.', 'success')
            return redirect(url_for('lista_productos'))
        except sqlite3.IntegrityError:
            flash('Error: El número de serie ya existe.', 'danger')
        except Exception as e:
            flash(f'Error al crear el producto: {e}', 'danger')
        return redirect(url_for('crear_producto'))

    # Lógica para GET
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tipos_producto = cur.execute("SELECT * FROM tipos_producto ORDER BY tipo_producto").fetchall()
        proveedores = cur.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()
        estados_equipo = cur.execute("SELECT * FROM estados_equipo ORDER BY nombre").fetchall()
        
    return render_template(
        'crear_producto.html',
        tipos_producto=tipos_producto,
        proveedores=proveedores,
        estados_equipo=estados_equipo,
        usuario=session.get('nombre'),
        permiso=session.get('permiso'),
        fecha=datetime.now().strftime('%d/%m/%Y %H:%M')
    )

# ============================================================================
# RUTAS - GESTIÓN DE PROVEEDORES
# ============================================================================

@app.route('/proveedor/nuevo', methods=['GET', 'POST'])
def crear_proveedor():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO proveedores (nombre, contacto, telefono, email, direccion)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    request.form['nombre'],
                    request.form.get('contacto'),
                    request.form.get('telefono'),
                    request.form.get('email'),
                    request.form.get('direccion')
                ))
                conn.commit()
            flash('Proveedor creado exitosamente.', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error al crear el proveedor: {e}', 'danger')
            return redirect(url_for('crear_proveedor'))
    
    return render_template('crear_proveedor.html')


# ============================================================================
# RUTAS - GESTIÓN DE INVENTARIO 
# ============================================================================
@app.route('/inventario/asignaciones')
def historico_asignaciones():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder a esta sección.', 'danger')
        return redirect(url_for('dashboard'))

    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                h.historico_id, p.nombre AS nombre_producto, tm.nombre AS tipo_movimiento,
                (SELECT pe.primer_nombre || ' ' || pe.apellido_pat FROM usuarios u JOIN personas pe ON u.persona_rut = pe.rut WHERE u.usuario_id = h.usuario_id) AS usuario_asignado,
                (SELECT pe.primer_nombre || ' ' || pe.apellido_pat FROM usuarios u JOIN personas pe ON u.persona_rut = pe.rut WHERE u.usuario_id = h.responsable_id) AS responsable,
                h.fecha_asignacion, h.fecha_devolucion
            FROM historico_asignaciones h
            JOIN productos p ON h.producto_id = p.producto_id
            LEFT JOIN tipos_movimiento tm ON h.tipo_movimiento_id = tm.tipo_movimiento_id
            ORDER BY h.fecha_asignacion DESC
        """)
        movimientos = cur.fetchall()

    return render_template('historico_asignaciones.html', movimientos=movimientos, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/inventario/asignaciones/nueva', methods=['GET', 'POST'])
def crear_asignacion():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder a esta sección.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        producto_id = request.form.get('producto_id')
        usuario_id = request.form.get('usuario_id')
        tipo_movimiento_id = request.form.get('tipo_movimiento_id')
        comentarios = request.form.get('comentarios')
        nombre_usuario_responsable = session.get('usuario')

        if not all([producto_id, usuario_id, tipo_movimiento_id]):
            flash('Producto, usuario asignado y tipo de movimiento son obligatorios.', 'danger')
            return redirect(url_for('crear_asignacion'))

        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                responsable_id = cur.execute("SELECT usuario_id FROM usuarios WHERE nombre_usuario = ?", (nombre_usuario_responsable,)).fetchone()[0]
                tipo_movimiento_nombre = cur.execute("SELECT nombre FROM tipos_movimiento WHERE tipo_movimiento_id = ?", (tipo_movimiento_id,)).fetchone()[0].lower()
                stock_actual = cur.execute("SELECT stock_actual FROM productos WHERE producto_id = ?", (producto_id,)).fetchone()[0]

                if 'asignacion' in tipo_movimiento_nombre or 'baja' in tipo_movimiento_nombre:
                    if stock_actual < 1:
                        flash('No se puede registrar la asignación. El producto no tiene stock.', 'danger')
                        return redirect(url_for('crear_asignacion'))
                    nuevo_stock = stock_actual - 1
                elif 'devolucion' in tipo_movimiento_nombre:
                    nuevo_stock = stock_actual + 1
                else:
                    nuevo_stock = stock_actual

                cur.execute("UPDATE productos SET stock_actual = ? WHERE producto_id = ?", (nuevo_stock, producto_id))
                cur.execute("INSERT INTO historico_asignaciones (usuario_id, producto_id, fecha_asignacion, tipo_movimiento_id, responsable_id, comentarios) VALUES (?, ?, ?, ?, ?, ?)",
                            (usuario_id, producto_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), tipo_movimiento_id, responsable_id, comentarios))
                conn.commit()
            flash('Asignación registrada exitosamente.', 'success')
            return redirect(url_for('historico_asignaciones'))
        except Exception as e:
            flash(f"Error al registrar la asignación: {e}", "danger")
            return redirect(url_for('crear_asignacion'))

    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        productos = cur.execute("SELECT producto_id, nombre, stock_actual FROM productos WHERE stock_actual > 0 ORDER BY nombre").fetchall()
        usuarios = cur.execute("SELECT u.usuario_id, p.primer_nombre || ' ' || p.apellido_pat as nombre_completo FROM usuarios u JOIN personas p ON u.persona_rut = p.rut ORDER BY nombre_completo").fetchall()
        tipos_movimiento = cur.execute("SELECT tipo_movimiento_id, nombre FROM tipos_movimiento ORDER BY nombre").fetchall()

    return render_template('crear_asignacion.html', productos=productos, usuarios=usuarios, tipos_movimiento=tipos_movimiento, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))


# ============================================================================
# RUTAS DE MARCADOR DE POSICIÓN PARA MÓDULOS FUTUROS
# ============================================================================
def placeholder_route():
    """Una ruta genérica para módulos en desarrollo."""
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    
    endpoint_name = request.endpoint.replace('_', ' ').title()
    flash(f'El módulo "{endpoint_name}" está en construcción.', 'info')
    return redirect(url_for('dashboard'))

# Asigna la misma función de marcador de posición a todas las rutas nuevas.
app.add_url_rule('/crear_activos', 'crear_activos', placeholder_route)
app.add_url_rule('/lista_activos', 'lista_activos', placeholder_route)
app.add_url_rule('/crear_lecturas', 'crear_lecturas', placeholder_route)
app.add_url_rule('/lista_lecturas', 'lista_lecturas', placeholder_route)
app.add_url_rule('/crear_personas', 'crear_personas', placeholder_route)
app.add_url_rule('/lista_personas', 'lista_personas', placeholder_route)
app.add_url_rule('/crear_reportes', 'crear_reportes', placeholder_route)
app.add_url_rule('/lista_reportes', 'lista_reportes', placeholder_route)


# ============================================================================
# RUTAS API - ESCANEOS (NFC/QR/BARCODE)
# ============================================================================
def _procesar_escaneo(data, tipo_scan):
    """Procesa y guarda cualquier tipo de escaneo (NFC, QR, Barcode)."""
    device_info = data.get('deviceInfo', {})
    content = data.get('content', '')
    
    scan_data = {
        'type': tipo_scan.upper(),
        'content': content,
        'scan_type': tipo_scan,
        'raw_data': data
    }
    
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    
    reading = db.save_reading(device_info, scan_data, ip_address, user_agent)
    socketio.emit('new_scan_reading', reading)
    
    return {
        'success': True,
        'message': f'Escaneo {tipo_scan} procesado correctamente.',
        'data': {
            'reading_id': reading['id'],
            'content': content,
            'timestamp': reading['timestamp']
        }
    }

@app.route('/api/scan', methods=['POST'])
def generic_scan_endpoint():
    """Endpoint genérico para cualquier tipo de escaneo."""
    try:
        data = request.json
        scan_type = data.get('type', 'unknown').lower()
        
        if scan_type not in ['nfc', 'qr', 'barcode']:
            scan_type = 'unknown'
            
        response_data = _procesar_escaneo(data, scan_type)
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error procesando escaneo: {str(e)}'
        }), 400

# ============================================================================
# RUTAS DE DESCARGA Y ESTADO DE APK
# ============================================================================
@app.route('/download-apk')
def download_apk():
    """Permite descargar el archivo APK si existe."""
    try:
        if APK_EXISTS:
            return send_file(APK_FILE, as_attachment=True, download_name='I-Tec-NFC-Scanner.apk')
        else:
            flash('El archivo APK no está disponible en el servidor.', 'warning')
            return redirect(url_for('login'))
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al descargar: {e}'}), 500

# ============================================================================
# EVENTOS DE WEBSOCKET
# ============================================================================
@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado: {request.sid}')
    emit('status', {'message': 'Conectado al servidor I-Tec'})
    emit('stats_update', db.get_stats())

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Cliente desconectado: {request.sid}')

# ============================================================================
# EJECUCIÓN PRINCIPAL
# ============================================================================
if __name__ == '__main__':
    init_inventory_db()

    print("=" * 60)
    print("🚀 I-Tec NFC Scanner - Servidor Unificado")
    print("=" * 60)
    print("Servidor escuchando en http://0.0.0.0:5001")
    print(f"🔑 Login: http://localhost:5001/login")
    print(f"📦 APK disponible: {'✅ Sí' if APK_EXISTS else '❌ No'}")
    print("=" * 60)
    
    socketio.run(app, 
                 host='0.0.0.0',
                 port=5001,
                 debug=True,
                 allow_unsafe_werkzeug=True)

