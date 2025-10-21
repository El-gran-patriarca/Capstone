# -*- coding: utf-8 -*-
"""
Esta es una aplicación Flask que sirve como backend para una aplicación de escaneo NFC.
Proporciona una interfaz web para la gestión de usuarios y un panel de control en tiempo real,
así como una API RESTful para recibir y procesar lecturas NFC desde una aplicación móvil.
También incluye autenticación de usuarios y manejo de sesiones.
"""
from werkzeug.security import generate_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, abort
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from datetime import datetime
import json
import os
import sqlite3
from io import BytesIO
import base64
# CORRECCIÓN: Asegúrate de que el nombre del archivo de autenticación sea el correcto.
from autentificacion import validar_credenciales, iniciar_sesion, cerrar_sesion, verificar_sesion, obtener_permisos_usuario, obtener_roles_modulos, obtener_rutas_modulos
from db import obtener_conexion
from pathlib import Path
import unicodedata
# ============================================================================
# FUNCIÓN AUXILIAR PARA VARIABLES DE SESIÓN
# ============================================================================
def session_vars():
    """Retorna un diccionario con las variables de sesión comunes para las plantillas."""
    return {
        'usuario': session.get('nombre'),
        'permiso': session.get('permiso'),
        'fecha': datetime.now().strftime('%d/%m/%Y %H:%M')
    }
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

            cur.execute('INSERT INTO usuarios (nombre_usuario, password, id_rol, activo, persona_rut, area_id, tienda_id, fecha_creacion) VALUES (?, ?, ?, ?, ?, ?, ?, datetime("now"))',
                        (nombre_usuario, password_hash, id_rol_val, form_data.get('activo', 'Activo'), rut, form_data.get('area_id'), form_data.get('tienda_id')))
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
        tiendas = cur.execute('SELECT tienda_id, nombre_tienda FROM tiendas ORDER BY nombre_tienda').fetchall()
        roles = [row['nombre_rol'] for row in cur.execute('SELECT nombre_rol FROM roles ORDER BY nombre_rol').fetchall()]

    return render_template('crear_usuario.html', areas=areas, tiendas=tiendas, roles=roles, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))


@app.route('/usuarios')
def lista_usuarios():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT u.nombre_usuario, p.rut AS persona_rut,
                p.primer_nombre || ' ' || p.apellido_pat AS nombre_completo, 
                r.nombre_rol, u.activo
            FROM usuarios u 
            JOIN personas p ON u.persona_rut = p.rut 
            LEFT JOIN roles r ON u.id_rol = r.id_rol
            ORDER BY p.primer_nombre
        """)
        usuarios = cur.fetchall()

    return render_template('lista_usuarios.html', usuarios=usuarios, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/gestion_usuarios')
def gestion_usuarios():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('gestion_usuarios.html', usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

# ELIMINAR PERSONA (y usuarios asociados)

@app.route('/personas/eliminar/<rut>', methods=['POST'])
def eliminar_persona(rut):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para esta acción.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        with obtener_conexion() as conn:
            conn.execute("PRAGMA foreign_keys = ON;")  # activa el borrado en cascada
            cur = conn.cursor()
            cur.execute("DELETE FROM personas WHERE rut = ?", (rut,))
            conn.commit()
        flash('Persona y usuarios asociados eliminados exitosamente.', 'success')
    except Exception as e:
        flash(f'Error al eliminar la persona: {e}', 'danger')

    return redirect(url_for('lista_usuarios'))



def _actualizar_usuario_db(nombre_usuario_actual, form_data):
    """Lógica de negocio para actualizar un usuario (tabla usuarios) y la información de la persona asociada (tabla personas)."""
    
    password = form_data.get('password')
    password2 = form_data.get('password2')
    rut = form_data.get('rut')
    
    if not rut:
         return False, 'Error interno: El RUT de la persona es requerido para la actualización.', nombre_usuario_actual

    if password and password != password2:
        return False, 'Las contraseñas no coinciden.', nombre_usuario_actual

    # Capturar el posible nuevo nombre de usuario. Si está vacío, usa el actual.
    nombre_usuario_nuevo = form_data.get('nombre_usuario_nuevo', '').strip() or nombre_usuario_actual

    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            
            # 1. Validación de unicidad de nombre de usuario si se intenta cambiar
            if nombre_usuario_nuevo != nombre_usuario_actual:
                existing_user = cur.execute("SELECT 1 FROM usuarios WHERE nombre_usuario = ?", (nombre_usuario_nuevo,)).fetchone()
                if existing_user:
                    return False, f'El nombre de usuario "{nombre_usuario_nuevo}" ya está en uso.', nombre_usuario_actual

            # 2. Obtener id_rol
            rol_result = cur.execute('SELECT id_rol FROM roles WHERE nombre_rol = ?', (form_data.get('rol'),)).fetchone()
            id_rol_val = rol_result[0] if rol_result else None

            # 3. Actualizar tabla PERSONAS (Usando el RUT)
            cur.execute('''
                UPDATE personas 
                SET 
                    primer_nombre = ?, segundo_nombre = ?, 
                    apellido_pat = ?, apellido_mat = ?, 
                    telefono = ?, correo = ? 
                WHERE 
                    rut = ?
            ''', (
                form_data.get('primer_nombre'), 
                form_data.get('segundo_nombre'), 
                form_data.get('apellido_pat'), 
                form_data.get('apellido_mat'), 
                form_data.get('telefono'), 
                form_data.get('correo'), 
                rut
            ))
            
            # 4. Actualizar tabla USUARIOS (Usando el nombre_usuario_actual)
            params = [
                id_rol_val,
                form_data.get('activo'),
                form_data.get('area_id'),
                form_data.get('tienda_id'),
            ]
            
            update_parts = [
                'id_rol = ?', 
                'activo = ?', 
                'area_id = ?', 
                'tienda_id = ?'
            ]

            # Si hay cambio de contraseña
            if password:
                # Reemplazar con tu función real de hashing
                password_hash = generate_password_hash(password) 
                update_parts.insert(0, 'password = ?')
                params.insert(0, password_hash)
            
            # Si hay cambio de nombre de usuario
            if nombre_usuario_nuevo != nombre_usuario_actual:
                update_parts.append('nombre_usuario = ?')
                params.append(nombre_usuario_nuevo)

            # Agregar la condición WHERE al final
            params.append(nombre_usuario_actual)

            # Ejecutar la actualización de usuarios
            update_query = f"UPDATE usuarios SET {', '.join(update_parts)} WHERE nombre_usuario = ?"
            cur.execute(update_query, tuple(params))

            conn.commit()
            
            return True, 'Usuario y datos personales actualizados exitosamente.', nombre_usuario_nuevo
    
    except Exception as e:
        return False, f'Error de base de datos: {e}', nombre_usuario_actual

@app.route('/usuarios/editar/<nombre_usuario>', methods=['GET', 'POST'])
def editar_usuario(nombre_usuario):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        # La función devuelve el nuevo nombre de usuario
        exito, mensaje, nombre_usuario_nuevo = _actualizar_usuario_db(nombre_usuario, request.form)
        flash(mensaje, 'success' if exito else 'danger')
        
        # Si la actualización fue exitosa y el nombre de usuario fue cambiado, redirigimos a la nueva URL
        if exito and nombre_usuario_nuevo != nombre_usuario:
            # Importante: Si el nombre cambió, redirigir a la nueva URL para evitar errores 404
            return redirect(url_for('lista_usuarios', nombre_usuario=nombre_usuario_nuevo))
        
        # Si hubo un error o el nombre no cambió, redirigimos a la misma página de edición
        return redirect(url_for('lista_usuarios', nombre_usuario=nombre_usuario_nuevo)) # Usamos el nuevo/actual nombre

    # Lógica GET para cargar los datos en el formulario
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Consulta para traer todos los datos (usuarios, personas, rol, tienda, area)
        usuario_data = cur.execute('''
            SELECT 
                u.*, 
                p.*, 
                r.nombre_rol, 
                t.nombre_tienda, 
                a.nombre_area 
            FROM usuarios u 
            JOIN personas p ON u.persona_rut = p.rut 
            LEFT JOIN roles r ON u.id_rol = r.id_rol 
            LEFT JOIN tiendas t ON u.tienda_id = t.tienda_id
            LEFT JOIN areas a ON u.area_id = a.area_id
            WHERE u.nombre_usuario = ?
        ''', (nombre_usuario,)).fetchone()
        
        if not usuario_data:
            flash('Usuario no encontrado.', 'danger')
            return redirect(url_for('lista_usuarios'))
        
        # Consultas para los select boxes
        areas = cur.execute('SELECT area_id, nombre_area AS nombre FROM areas ORDER BY nombre_area').fetchall()
        tiendas = cur.execute('SELECT tienda_id, nombre_tienda FROM tiendas ORDER BY nombre_tienda').fetchall() 
        roles = [row['nombre_rol'] for row in cur.execute('SELECT nombre_rol FROM roles ORDER BY nombre_rol').fetchall()]

    return render_template('editar_usuario.html', 
                           usuario_data=usuario_data, 
                           areas=areas, 
                           tiendas=tiendas, 
                           roles=roles, 
                           usuario=session.get('nombre'), 
                           permiso=session.get('permiso'), 
                           fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

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
            return redirect(url_for('lista_areas'))
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

# NUEVAS RUTAS PARA GESTIÓN DE ÁREAS

@app.route('/areas')
def lista_areas():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT area_id, nombre_area FROM areas ORDER BY nombre_area")
        areas = cur.fetchall()

    return render_template('lista_areas.html', areas=areas, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/areas/editar/<int:area_id>', methods=['GET', 'POST'])
def editar_area(area_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        if not nombre:
            flash('El nombre del área no puede estar vacío.', 'warning')
        else:
            try:
                cur.execute("UPDATE areas SET nombre_area = ? WHERE area_id = ?", (nombre, area_id))
                conn.commit()
                flash('Área actualizada exitosamente.', 'success')
                return redirect(url_for('lista_areas'))
            except sqlite3.IntegrityError:
                flash('El nombre de esa área ya existe.', 'danger')
            except Exception as e:
                flash(f'Error al actualizar el área: {e}', 'danger')
            finally:
                conn.close()
        return redirect(url_for('editar_area', area_id=area_id))

    # Método GET
    area = cur.execute("SELECT * FROM areas WHERE area_id = ?", (area_id,)).fetchone()
    conn.close()
    if not area:
        flash('Área no encontrada.', 'danger')
        return redirect(url_for('lista_areas'))
    
    return render_template('editar_area.html', area=area, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/areas/eliminar/<int:area_id>', methods=['POST'])
def eliminar_area(area_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            # Opcional: Verificar si el área está en uso antes de eliminar
            en_uso = cur.execute("SELECT 1 FROM usuarios WHERE area_id = ?", (area_id,)).fetchone()
            if en_uso:
                flash('No se puede eliminar el área porque está asignada a uno o más usuarios.', 'warning')
                return redirect(url_for('lista_areas'))
            
            cur.execute("DELETE FROM areas WHERE area_id = ?", (area_id,))
            conn.commit()
        flash('Área eliminada exitosamente.', 'success')
    except Exception as e:
        flash(f'Error al eliminar el área: {e}', 'danger')

    return redirect(url_for('lista_areas'))
# NUEVAS RUTAS PARA GESTIÓN DE ROLES

@app.route('/roles')
def lista_roles():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))
    
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id_rol, nombre_rol FROM roles ORDER BY nombre_rol")
        roles = cur.fetchall()

    return render_template('lista_roles.html', roles=roles, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/roles/editar/<int:rol_id>', methods=['GET', 'POST'])
def editar_rol(rol_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        if not nombre:
            flash('El nombre del rol no puede estar vacío.', 'warning')
        else:
            try:
                cur.execute("UPDATE roles SET nombre_rol = ? WHERE id_rol = ?", (nombre, rol_id))
                conn.commit()
                flash('Rol actualizado exitosamente.', 'success')
                return redirect(url_for('lista_roles'))
            except sqlite3.IntegrityError:
                flash('El nombre de ese rol ya existe.', 'danger')
            except Exception as e:
                flash(f'Error al actualizar el rol: {e}', 'danger')
            finally:
                conn.close()
        return redirect(url_for('editar_rol', rol_id=rol_id))

    # Método GET
    rol = cur.execute("SELECT * FROM roles WHERE id_rol = ?", (rol_id,)).fetchone()
    conn.close()
    if not rol:
        flash('Rol no encontrado.', 'danger')
        return redirect(url_for('lista_roles'))
    
    return render_template('editar_rol.html', rol=rol, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/roles/eliminar/<int:rol_id>', methods=['POST'])
def eliminar_rol(rol_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            # Opcional: Verificar si el rol está en uso antes de eliminar
            en_uso = cur.execute("SELECT 1 FROM usuarios WHERE id_rol = ?", (rol_id,)).fetchone()
            if en_uso:
                flash('No se puede eliminar el rol porque está asignado a uno o más usuarios.', 'warning')
                return redirect(url_for('lista_roles'))
            
            cur.execute("DELETE FROM roles WHERE id_rol = ?", (rol_id,))
            conn.commit()
        flash('Rol eliminado exitosamente.', 'success')
    except Exception as e:
        flash(f'Error al eliminar el rol: {e}', 'danger')

    return redirect(url_for('lista_roles'))
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
            return redirect(url_for('lista_roles'))
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
                tp.nombre_producto as tipo_producto,
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
        tipos_producto = cur.execute("SELECT * FROM tipos_producto ORDER BY nombre_producto").fetchall()
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
    
# NUEVA RUTA PARA EDITAR UN PRODUCTO
@app.route('/productos/editar/<int:producto_id>', methods=['GET', 'POST'])
def editar_producto(producto_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para acceder.', 'danger')
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if request.method == 'POST':
        try:
            cur.execute("""
                UPDATE productos SET
                    nombre = ?, tipo_producto_id = ?, numero_serie = ?, numero_factura = ?, 
                    fecha_compra = ?, valor_unitario = ?, proveedor_id = ?, garantia_hasta = ?, 
                    estado_equipo_id = ?, ubicacion_fisica = ?, stock_actual = ?,
                    updated_at = datetime('now')
                WHERE producto_id = ?
            """, (
                request.form['nombre'], request.form['tipo_producto_id'],
                request.form['numero_serie'], request.form['numero_factura'],
                request.form['fecha_compra'], request.form['valor_unitario'],
                request.form.get('proveedor_id'), request.form.get('garantia_hasta'),
                request.form['estado_equipo_id'], request.form.get('ubicacion_fisica'),
                request.form.get('stock_actual', 1), producto_id
            ))
            conn.commit()
            flash('Producto actualizado exitosamente.', 'success')
            return redirect(url_for('lista_productos'))
        except sqlite3.IntegrityError:
            flash('Error: El número de serie ya existe en otro producto.', 'danger')
        except Exception as e:
            flash(f'Error al actualizar el producto: {e}', 'danger')
        finally:
            conn.close()
        return redirect(url_for('editar_producto', producto_id=producto_id))

    # Lógica para GET
    producto = cur.execute("SELECT * FROM productos WHERE producto_id = ?", (producto_id,)).fetchone()
    if not producto:
        flash('Producto no encontrado.', 'danger')
        return redirect(url_for('lista_productos'))

    tipos_producto = cur.execute("SELECT * FROM tipos_producto ORDER BY nombre_producto").fetchall()
    proveedores = cur.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()
    estados_equipo = cur.execute("SELECT * FROM estados_equipo ORDER BY nombre").fetchall()
    conn.close()
    
    return render_template(
        'editar_producto.html',
        producto=producto,
        tipos_producto=tipos_producto,
        proveedores=proveedores,
        estados_equipo=estados_equipo,
        usuario=session.get('nombre'),
        permiso=session.get('permiso'),
        fecha=datetime.now().strftime('%d/%m/%Y %H:%M')
    )

# NUEVA RUTA PARA ELIMINAR UN PRODUCTO
@app.route('/productos/eliminar/<int:producto_id>', methods=['POST'])
def eliminar_producto(producto_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para esta acción.', 'danger')
        return redirect(url_for('lista_productos'))
    
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            # Opcional: Primero verifica si el producto no está asignado
            asignacion = cur.execute("SELECT 1 FROM historico_asignaciones WHERE producto_id = ? AND fecha_devolucion IS NULL", (producto_id,)).fetchone()
            if asignacion:
                flash('No se puede eliminar un producto que está actualmente asignado.', 'warning')
                return redirect(url_for('lista_productos'))
            
            cur.execute("DELETE FROM productos WHERE producto_id = ?", (producto_id,))
            conn.commit()
        flash('Producto eliminado exitosamente.', 'success')
    except Exception as e:
        flash(f'Error al eliminar el producto: {e}', 'danger')

    return redirect(url_for('lista_productos'))
# ============================================================================
# RUTAS - GESTIÓN DE TIPOS DE PRODUCTO
# ============================================================================
@app.route('/tipos-producto/nuevo', methods=['GET', 'POST'])
def crear_tipo_producto():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nombre_tipo = request.form['nombre'].strip()
        if nombre_tipo:
            # CORRECCIÓN: El campo en la BD es nombre_producto
            tipo_categoria = 'Activo Fijo' # Puedes cambiar esto o añadir otro campo en el formulario
            try:
                with obtener_conexion() as conn:
                    conn.execute("INSERT INTO tipos_producto (nombre_producto, tipo_producto) VALUES (?, ?)", (nombre_tipo, tipo_categoria))
                flash('Tipo de producto creado exitosamente.', 'success')
                return redirect(url_for('lista_tipos_producto'))
            except sqlite3.IntegrityError:
                flash('Ese tipo de producto ya existe.', 'danger')
            except Exception as e:
                flash(f'Error: {e}', 'danger')
        else:
            flash('El nombre no puede estar vacío.', 'warning')
        # Si hay un error, redirige de nuevo al formulario de creación
        return redirect(url_for('crear_tipo_producto'))
    
    # CORRECCIÓN: Cuando la solicitud es GET, muestra el formulario de creación.
    return render_template('crear_tipo_producto.html', usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/tipos-producto')
def lista_tipos_producto():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        tipos_producto = conn.execute("SELECT * FROM tipos_producto ORDER BY nombre_producto").fetchall()

    return render_template('lista_tipos_producto.html', tipos_producto=tipos_producto, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))


@app.route('/tipos-producto/editar/<int:tipo_id>', methods=['GET', 'POST'])
def editar_tipo_producto(tipo_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        if nombre:
            try:
                conn.execute("UPDATE tipos_producto SET nombre_producto = ? WHERE tipo_producto_id = ?", (nombre, tipo_id))
                conn.commit()
                flash('Tipo de producto actualizado.', 'success')
            except Exception as e:
                flash(f'Error al actualizar: {e}', 'danger')
        else:
            flash('El nombre no puede estar vacío.', 'warning')
        conn.close()
        return redirect(url_for('lista_tipos_producto'))

    tipo = conn.execute("SELECT * FROM tipos_producto WHERE tipo_producto_id = ?", (tipo_id,)).fetchone()
    conn.close()
    if not tipo:
        return redirect(url_for('lista_tipos_producto'))
        
    return render_template('editar_tipo_producto.html', tipo=tipo, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/tipos-producto/eliminar/<int:tipo_id>', methods=['POST'])
def eliminar_tipo_producto(tipo_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    
    try:
        with obtener_conexion() as conn:
            # Opcional: Verificar si el tipo está en uso
            en_uso = conn.execute("SELECT 1 FROM productos WHERE tipo_producto_id = ?", (tipo_id,)).fetchone()
            if en_uso:
                flash('No se puede eliminar, este tipo está siendo usado por productos existentes.', 'warning')
                return redirect(url_for('lista_tipos_producto'))
            
            conn.execute("DELETE FROM tipos_producto WHERE tipo_producto_id = ?", (tipo_id,))
        flash('Tipo de producto eliminado.', 'success')
    except Exception as e:
        flash(f'Error al eliminar: {e}', 'danger')

    return redirect(url_for('lista_tipos_producto'))
# ============================================================================
# RUTAS - GESTIÓN DE ESTADOS DE EQUIPO
# ============================================================================
@app.route('/estados-equipo/nuevo', methods=['GET', 'POST'])
def crear_estado_equipo():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nombre_estado = request.form['nombre'].strip()
        if nombre_estado:
            try:
                with obtener_conexion() as conn:
                    conn.execute("INSERT INTO estados_equipo (nombre) VALUES (?)", (nombre_estado,))
                flash('Estado de equipo creado exitosamente.', 'success')
            except sqlite3.IntegrityError:
                flash('Ese estado ya existe.', 'danger')
            except Exception as e:
                flash(f'Error: {e}', 'danger')
        else:
            flash('El nombre no puede estar vacío.', 'warning')
        return redirect(url_for('lista_estados_equipo'))
    
    return render_template('crear_estado_equipo.html', usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))


@app.route('/estados-equipo')
def lista_estados_equipo():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        estados = conn.execute("SELECT * FROM estados_equipo ORDER BY nombre").fetchall()

    return render_template('lista_estados_equipo.html', estados=estados, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))


@app.route('/estados-equipo/editar/<int:estado_id>', methods=['GET', 'POST'])
def editar_estado_equipo(estado_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        if nombre:
            try:
                conn.execute("UPDATE estados_equipo SET nombre = ? WHERE estado_equipo_id = ?", (nombre, estado_id))
                conn.commit()
                flash('Estado actualizado.', 'success')
            except Exception as e:
                flash(f'Error al actualizar: {e}', 'danger')
        else:
            flash('El nombre no puede estar vacío.', 'warning')
        conn.close()
        return redirect(url_for('lista_estados_equipo'))

    estado = conn.execute("SELECT * FROM estados_equipo WHERE estado_equipo_id = ?", (estado_id,)).fetchone()
    conn.close()
    if not estado:
        return redirect(url_for('lista_estados_equipo'))
        
    return render_template('editar_estado_equipo.html', estado=estado, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/estados-equipo/eliminar/<int:estado_id>', methods=['POST'])
def eliminar_estado_equipo(estado_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    
    try:
        with obtener_conexion() as conn:
            en_uso = conn.execute("SELECT 1 FROM productos WHERE estado_equipo_id = ?", (estado_id,)).fetchone()
            if en_uso:
                flash('No se puede eliminar, este estado está siendo usado por productos existentes.', 'warning')
                return redirect(url_for('lista_estados_equipo'))
            
            conn.execute("DELETE FROM estados_equipo WHERE estado_equipo_id = ?", (estado_id,))
        flash('Estado de equipo eliminado.', 'success')
    except Exception as e:
        flash(f'Error al eliminar: {e}', 'danger')

    return redirect(url_for('lista_estados_equipo'))

# ============================================================================
# RUTAS - GESTIÓN DE PROVEEDORES
# ============================================================================
@app.route('/proveedores/nuevo', methods=['GET', 'POST'])
def crear_proveedor():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        if nombre:
            try:
                with obtener_conexion() as conn:
                    conn.execute(
                        "INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES (?, ?, ?, ?)",
                        (nombre, request.form.get('contacto'), request.form.get('telefono'), request.form.get('email'))
                    )
                flash('Proveedor creado exitosamente.', 'success')
            except sqlite3.IntegrityError:
                flash('Ese proveedor ya existe.', 'danger')
            except Exception as e:
                flash(f'Error: {e}', 'danger')
        else:
            flash('El nombre del proveedor no puede estar vacío.', 'warning')
        return redirect(url_for('lista_proveedores'))
    
    return render_template('crear_proveedor.html', usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/proveedores')
def lista_proveedores():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        proveedores = conn.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()

    return render_template('lista_proveedores.html', proveedores=proveedores, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/proveedores/editar/<int:proveedor_id>', methods=['GET', 'POST'])
def editar_proveedor(proveedor_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        if nombre:
            try:
                conn.execute(
                    "UPDATE proveedores SET nombre=?, contacto=?, telefono=?, email=? WHERE proveedor_id=?",
                    (nombre, request.form.get('contacto'), request.form.get('telefono'), request.form.get('email'), proveedor_id)
                )
                conn.commit()
                flash('Proveedor actualizado.', 'success')
            except Exception as e:
                flash(f'Error al actualizar: {e}', 'danger')
        else:
            flash('El nombre no puede estar vacío.', 'warning')
        conn.close()
        return redirect(url_for('lista_proveedores'))

    proveedor = conn.execute("SELECT * FROM proveedores WHERE proveedor_id = ?", (proveedor_id,)).fetchone()
    conn.close()
    if not proveedor:
        return redirect(url_for('lista_proveedores'))
        
    return render_template('editar_proveedor.html', proveedor=proveedor, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/proveedores/eliminar/<int:proveedor_id>', methods=['POST'])
def eliminar_proveedor(proveedor_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    
    try:
        with obtener_conexion() as conn:
            en_uso = conn.execute("SELECT 1 FROM productos WHERE proveedor_id = ?", (proveedor_id,)).fetchone()
            if en_uso:
                flash('No se puede eliminar, este proveedor está asociado a productos existentes.', 'warning')
                return redirect(url_for('lista_proveedores'))
            
            conn.execute("DELETE FROM proveedores WHERE proveedor_id = ?", (proveedor_id,))
        flash('Proveedor eliminado.', 'success')
    except Exception as e:
        flash(f'Error al eliminar: {e}', 'danger')

    return redirect(url_for('lista_proveedores'))
# ============================================================================
# RUTAS - GESTIÓN DE TIENDAS
# ============================================================================
@app.route('/tiendas')
def lista_tiendas():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        tiendas = conn.execute("SELECT * FROM tiendas ORDER BY nombre_tienda").fetchall()
    return render_template('lista_tiendas.html', tiendas=tiendas, **session_vars())

@app.route('/tiendas/nueva', methods=['GET', 'POST'])
def crear_tienda():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nombre = request.form['nombre_tienda'].strip()
        direccion = request.form.get('direccion', '').strip()
        if nombre:
            try:
                with obtener_conexion() as conn:
                    conn.execute("INSERT INTO tiendas (nombre_tienda, direccion) VALUES (?, ?)", (nombre, direccion))
                flash('Tienda creada exitosamente.', 'success')
                return redirect(url_for('lista_tiendas'))
            except sqlite3.IntegrityError:
                flash('El nombre de la tienda ya existe.', 'danger')
        else:
            flash('El nombre de la tienda es obligatorio.', 'warning')
    return render_template('crear_tienda.html', **session_vars())

@app.route('/tiendas/editar/<int:tienda_id>', methods=['GET', 'POST'])
def editar_tienda(tienda_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    if request.method == 'POST':
        nombre = request.form['nombre_tienda'].strip()
        direccion = request.form.get('direccion', '').strip()
        if nombre:
            try:
                conn.execute("UPDATE tiendas SET nombre_tienda = ?, direccion = ? WHERE tienda_id = ?", (nombre, direccion, tienda_id))
                conn.commit()
                flash('Tienda actualizada.', 'success')
                return redirect(url_for('lista_tiendas'))
            except sqlite3.IntegrityError:
                flash('El nombre de la tienda ya existe.', 'danger')
        else:
            flash('El nombre no puede estar vacío.', 'warning')
        conn.close()

    tienda = conn.execute("SELECT * FROM tiendas WHERE tienda_id = ?", (tienda_id,)).fetchone()
    conn.close()
    if not tienda:
        return redirect(url_for('lista_tiendas'))
    return render_template('editar_tienda.html', tienda=tienda, **session_vars())

@app.route('/productos/enviar-tienda/<int:producto_id>', methods=['GET', 'POST'])
def enviar_producto_tienda(producto_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row

    if request.method == 'POST':
        tienda_id = request.form.get('tienda_id')
        cantidad_a_enviar = int(request.form.get('cantidad', 0))

        producto = conn.execute("SELECT stock_actual FROM productos WHERE producto_id = ?", (producto_id,)).fetchone()

        if cantidad_a_enviar <= 0:
            flash('La cantidad debe ser mayor que cero.', 'warning')
        elif cantidad_a_enviar > producto['stock_actual']:
            flash('No puedes enviar más productos de los que hay en stock.', 'danger')
        else:
            try:
                # Descontar stock de la bodega principal
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE producto_id = ?", (cantidad_a_enviar, producto_id))
                # Registrar el envío en el historial
                usuario_id = conn.execute("SELECT usuario_id FROM usuarios WHERE nombre_usuario = ?", (session['usuario'],)).fetchone()['usuario_id']
                conn.execute(
                    "INSERT INTO envios_tienda (producto_id, tienda_id, cantidad_enviada, usuario_id) VALUES (?, ?, ?, ?)",
                    (producto_id, tienda_id, cantidad_a_enviar, usuario_id)
                )
                conn.commit()
                flash(f'Se enviaron {cantidad_a_enviar} unidades a la tienda exitosamente.', 'success')
                return redirect(url_for('lista_productos'))
            except Exception as e:
                flash(f'Error al procesar el envío: {e}', 'danger')

        conn.close()
        return redirect(url_for('enviar_producto_tienda', producto_id=producto_id))

    # Método GET
    producto = conn.execute("SELECT * FROM productos WHERE producto_id = ?", (producto_id,)).fetchone()
    tiendas = conn.execute("SELECT * FROM tiendas ORDER BY nombre_tienda").fetchall()
    conn.close()

    if not producto:
        return redirect(url_for('lista_productos'))

    return render_template('enviar_producto_tienda.html', producto=producto, tiendas=tiendas, **session_vars())

# ============================================================================
# RUTA - REPORTE DE UBICACIÓN DE INVENTARIO
# ============================================================================
@app.route('/inventario/ubicacion')
def inventario_ubicacion():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        flash('No tienes permisos para ver este reporte.', 'danger')
        return redirect(url_for('dashboard'))

    inventario = []
    try:
        with obtener_conexion() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Esta consulta es compleja. Usa UNION ALL para combinar resultados de diferentes "ubicaciones".
            # 1. Productos en Bodega
            # 2. Productos Asignados a Usuarios
            # 3. Productos en Mantenimiento
            # 4. Resumen de productos en Tiendas
            cur.execute("""
                -- 1. Productos asignados a usuarios
                SELECT
                    p.nombre AS nombre_producto,
                    p.numero_serie,
                    'Asignado' AS ubicacion,
                    per.primer_nombre || ' ' || per.apellido_pat AS detalle
                FROM productos p
                JOIN historico_asignaciones ha ON p.producto_id = ha.producto_id
                JOIN usuarios u ON ha.usuario_id = u.usuario_id
                JOIN personas per ON u.persona_rut = per.rut
                WHERE ha.fecha_devolucion IS NULL

                UNION ALL

                -- 2. Productos en mantenimiento
                SELECT
                    p.nombre AS nombre_producto,
                    p.numero_serie,
                    'En Mantenimiento' AS ubicacion,
                    'Asignado a técnico ID ' || m.tecnico_id AS detalle
                FROM productos p
                JOIN mantenimientos m ON p.producto_id = m.producto_id
                WHERE m.fecha_fin IS NULL

                UNION ALL

                -- 3. Productos en Bodega Principal (que no están asignados ni en mantenimiento)
                SELECT
                    p.nombre AS nombre_producto,
                    p.numero_serie,
                    'Bodega' AS ubicacion,
                    p.ubicacion_fisica AS detalle
                FROM productos p
                WHERE p.producto_id NOT IN (
                    SELECT producto_id FROM historico_asignaciones WHERE fecha_devolucion IS NULL
                ) AND p.producto_id NOT IN (
                    SELECT producto_id FROM mantenimientos WHERE fecha_fin IS NULL
                ) AND p.stock_actual > 0

                UNION ALL

                -- 4. Resumen de stock en tiendas
                SELECT
                    p.nombre AS nombre_producto,
                    'N/A (Stock por cantidad)' AS numero_serie,
                    'En Tienda' AS ubicacion,
                    t.nombre_tienda || ' (Cantidad: ' || SUM(et.cantidad_enviada) || ')' AS detalle
                FROM envios_tienda et
                JOIN productos p ON et.producto_id = p.producto_id
                JOIN tiendas t ON et.tienda_id = t.tienda_id
                GROUP BY p.producto_id, t.tienda_id
            """)
            inventario = cur.fetchall()

    except Exception as e:
        flash(f'Error al generar el reporte de inventario: {e}', 'danger')

    return render_template('inventario_ubicacion.html', inventario=inventario, **session_vars())

@app.route('/inventario/tiendas')
def stock_tiendas():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    stock_por_tienda = []
    try:
        with obtener_conexion() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Primero, obtenemos todas las tiendas
            tiendas = cur.execute("SELECT * FROM tiendas ORDER BY nombre_tienda").fetchall()

            for tienda in tiendas:
                # Por cada tienda, calculamos el stock de sus productos
                productos_en_tienda = cur.execute("""
                    SELECT
                        p.producto_id,
                        p.nombre as nombre_producto,
                        SUM(CASE WHEN et.envio_id IS NOT NULL THEN et.cantidad_enviada ELSE 0 END) -
                        SUM(CASE WHEN rt.retiro_id IS NOT NULL AND rt.estado = 'Completado' THEN rt.cantidad_retirada ELSE 0 END) as stock_en_tienda
                    FROM productos p
                    LEFT JOIN envios_tienda et ON p.producto_id = et.producto_id AND et.tienda_id = ?
                    LEFT JOIN retiros_tienda rt ON p.producto_id = rt.producto_id AND rt.tienda_id = ?
                    WHERE et.tienda_id = ? OR rt.tienda_id = ?
                    GROUP BY p.producto_id, p.nombre
                    HAVING stock_en_tienda > 0
                """, (tienda['tienda_id'], tienda['tienda_id'], tienda['tienda_id'], tienda['tienda_id'])).fetchall()

                if productos_en_tienda:
                    stock_por_tienda.append({
                        'tienda_id': tienda['tienda_id'],
                        'nombre_tienda': tienda['nombre_tienda'],
                        'productos': productos_en_tienda
                    })
    except Exception as e:
        flash(f'Error al cargar el stock de tiendas: {e}', 'danger')

    return render_template('stock_tiendas.html', stock_por_tienda=stock_por_tienda, **session_vars())

@app.route('/retiros/nuevo/<int:producto_id>/<int:tienda_id>', methods=['GET', 'POST'])
def crear_retiro_tienda(producto_id, tienda_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Calcular stock actual en la tienda para validación
    stock_info = cur.execute("""
        SELECT
            SUM(CASE WHEN et.envio_id IS NOT NULL THEN et.cantidad_enviada ELSE 0 END) -
            SUM(CASE WHEN rt.retiro_id IS NOT NULL AND rt.estado = 'Completado' THEN rt.cantidad_retirada ELSE 0 END) as stock_actual
        FROM productos p
        LEFT JOIN envios_tienda et ON p.producto_id = et.producto_id AND et.tienda_id = ?
        LEFT JOIN retiros_tienda rt ON p.producto_id = rt.producto_id AND rt.tienda_id = ?
        WHERE p.producto_id = ?
    """, (tienda_id, tienda_id, producto_id)).fetchone()
    stock_tienda = stock_info['stock_actual'] if stock_info else 0

    if request.method == 'POST':
        cantidad_a_retirar = int(request.form.get('cantidad', 0))
        if 0 < cantidad_a_retirar <= stock_tienda:
            try:
                usuario_id = cur.execute("SELECT usuario_id FROM usuarios WHERE nombre_usuario = ?", (session['usuario'],)).fetchone()['usuario_id']
                cur.execute(
                    "INSERT INTO retiros_tienda (producto_id, tienda_id, cantidad_retirada, usuario_solicitante_id) VALUES (?, ?, ?, ?)",
                    (producto_id, tienda_id, cantidad_a_retirar, usuario_id)
                )
                conn.commit()
                flash('Solicitud de retiro creada exitosamente.', 'success')
                return redirect(url_for('stock_tiendas'))
            except Exception as e:
                flash(f'Error al crear la solicitud: {e}', 'danger')
        else:
            flash('La cantidad a retirar no es válida.', 'warning')
        conn.close()
        return redirect(url_for('crear_retiro_tienda', producto_id=producto_id, tienda_id=tienda_id))

    # Método GET
    producto = cur.execute("SELECT * FROM productos WHERE producto_id = ?", (producto_id,)).fetchone()
    tienda = cur.execute("SELECT * FROM tiendas WHERE tienda_id = ?", (tienda_id,)).fetchone()
    conn.close()
    return render_template('crear_retiro_tienda.html', producto=producto, tienda=tienda, stock_tienda=stock_tienda, **session_vars())

@app.route('/retiros/pendientes')
def lista_retiros_pendientes():
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        retiros = conn.execute("""
            SELECT rt.*, p.nombre as nombre_producto, t.nombre_tienda
            FROM retiros_tienda rt
            JOIN productos p ON rt.producto_id = p.producto_id
            JOIN tiendas t ON rt.tienda_id = t.tienda_id
            WHERE rt.estado = 'Pendiente'
            ORDER BY rt.fecha_solicitud ASC
        """).fetchall()
    return render_template('lista_retiros_pendientes.html', retiros=retiros, **session_vars())

@app.route('/retiros/confirmar/<int:retiro_id>', methods=['POST'])
def confirmar_recepcion_retiro(retiro_id):
    if not verificar_sesion() or obtener_permisos_usuario() != 'admin':
        return redirect(url_for('dashboard'))
    
    try:
        # Usamos 'obtener_conexion()' en lugar de 'with' para poder configurar el row_factory
        conn = obtener_conexion()
        # LA CORRECCIÓN CLAVE ESTÁ AQUÍ:
        conn.row_factory = sqlite3.Row
        
        cur = conn.cursor()
        retiro = cur.execute("SELECT * FROM retiros_tienda WHERE retiro_id = ? AND estado = 'Pendiente'", (retiro_id,)).fetchone()
        
        if retiro:
            # Ahora retiro['cantidad_retirada'] y retiro['producto_id'] funcionarán
            # Actualizar stock en bodega principal
            cur.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE producto_id = ?", (retiro['cantidad_retirada'], retiro['producto_id']))
            
            # Marcar retiro como completado
            usuario_id = cur.execute("SELECT usuario_id FROM usuarios WHERE nombre_usuario = ?", (session['usuario'],)).fetchone()['usuario_id']
            cur.execute(
                "UPDATE retiros_tienda SET estado = 'Completado', fecha_recepcion = datetime('now'), usuario_receptor_id = ? WHERE retiro_id = ?",
                (usuario_id, retiro_id)
            )
            conn.commit()
            flash('Recepción confirmada y stock de bodega actualizado.', 'success')
        else:
            flash('El retiro no se encontró o ya fue procesado.', 'warning')
            
    except Exception as e:
        flash(f'Error al confirmar la recepción: {e}', 'danger')
    finally:
        # Asegurarnos de cerrar la conexión
        if conn:
            conn.close()
    
    return redirect(url_for('lista_retiros_pendientes'))
# ============================================================================
# RUTAS - GESTIÓN DE INVENTARIO (ADAPTADO A TU ESQUEMA DE BD)
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
# RUTAS - GESTIÓN DE MANTENIMIENTOS
# ============================================================================

@app.route('/mantenimientos')
def lista_mantenimientos():
    if not verificar_sesion():
        return redirect(url_for('login'))
    
    # Solo admin y tecnico pueden ver esta página
    if obtener_permisos_usuario() not in ['admin', 'tecnico']:
        flash('No tienes permisos para acceder a esta sección.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        with obtener_conexion() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Si es admin, ve todos los mantenimientos. Si es técnico, solo los suyos.
            if obtener_permisos_usuario() == 'admin':
                cur.execute("""
                    SELECT m.mantenimiento_id, p.nombre as nombre_producto, p.numero_serie, m.fecha_inicio, m.fecha_fin
                    FROM mantenimientos m
                    JOIN productos p ON m.producto_id = p.producto_id
                    ORDER BY m.fecha_inicio DESC
                """)
            else:
                usuario_actual_id = cur.execute("SELECT usuario_id FROM usuarios WHERE nombre_usuario = ?", (session.get('usuario'),)).fetchone()['usuario_id']
                cur.execute("""
                    SELECT m.mantenimiento_id, p.nombre as nombre_producto, p.numero_serie, m.fecha_inicio, m.fecha_fin
                    FROM mantenimientos m
                    JOIN productos p ON m.producto_id = p.producto_id
                    WHERE m.tecnico_id = ?
                    ORDER BY m.fecha_inicio DESC
                """, (usuario_actual_id,))
            
            mantenimientos = cur.fetchall()
    except Exception as e:
        flash(f"Error al cargar los mantenimientos: {e}", "danger")
        mantenimientos = []

    return render_template('lista_mantenimientos.html', mantenimientos=mantenimientos, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/mantenimiento/<int:mantenimiento_id>', methods=['GET', 'POST'])
def detalle_mantenimiento(mantenimiento_id):
    if not verificar_sesion() or obtener_permisos_usuario() not in ['admin', 'tecnico']:
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if request.method == 'POST':
        descripcion = request.form.get('descripcion')
        finalizado = 'finalizado' in request.form
        fecha_fin = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if finalizado else None

        try:
            cur.execute("""
                UPDATE mantenimientos 
                SET descripcion = ?, fecha_fin = ?
                WHERE mantenimiento_id = ?
            """, (descripcion, fecha_fin, mantenimiento_id))
            
            # Si se finaliza, se actualiza el estado del producto a "Disponible"
            if finalizado:
                # Asumimos que el estado "Disponible" tiene el id 2. ¡Verifica esto en tu BD!
                estado_disponible_id = 2 
                producto_id = cur.execute("SELECT producto_id FROM mantenimientos WHERE mantenimiento_id = ?", (mantenimiento_id,)).fetchone()['producto_id']
                cur.execute("UPDATE productos SET estado_equipo_id = ? WHERE producto_id = ?", (estado_disponible_id, producto_id))

            conn.commit()
            flash('Mantenimiento actualizado exitosamente.', 'success')
            return redirect(url_for('lista_mantenimientos'))
        except Exception as e:
            flash(f'Error al actualizar: {e}', 'danger')
        finally:
            conn.close()
        return redirect(url_for('detalle_mantenimiento', mantenimiento_id=mantenimiento_id))

    # Método GET
    mantenimiento = cur.execute("""
        SELECT m.*, p.nombre as nombre_producto, p.numero_serie
        FROM mantenimientos m
        JOIN productos p ON m.producto_id = p.producto_id
        WHERE m.mantenimiento_id = ?
    """, (mantenimiento_id,)).fetchone()
    conn.close()

    if not mantenimiento:
        flash('Tarea de mantenimiento no encontrada.', 'danger')
        return redirect(url_for('lista_mantenimientos'))

    return render_template('detalle_mantenimiento.html', mantenimiento=mantenimiento, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))
# RUTA PARA CREAR UN NUEVO MANTENIMIENTO (VISTA DE ADMIN)
@app.route('/mantenimientos/nuevo', methods=['GET', 'POST'])
def crear_mantenimiento():
    if not verificar_sesion() or obtener_permisos_usuario() not in ['admin', 'tecnico']:
        flash('Solo los administradores pueden asignar tareas de mantenimiento.', 'danger')
        return redirect(url_for('dashboard'))

    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if request.method == 'POST':
        producto_id = request.form.get('producto_id')
        tecnico_id = request.form.get('tecnico_id')
        descripcion = request.form.get('descripcion')
        
        # Asumimos que el estado "En reparación" tiene el id 3. ¡Verifícalo en tu BD!
        estado_reparacion_id = 3

        try:
            # Insertar en la tabla de mantenimientos
            cur.execute(
                "INSERT INTO mantenimientos (producto_id, tecnico_id, descripcion, fecha_inicio) VALUES (?, ?, ?, datetime('now'))",
                (producto_id, tecnico_id, descripcion)
            )
            # Actualizar el estado del producto
            cur.execute("UPDATE productos SET estado_equipo_id = ? WHERE producto_id = ?", (estado_reparacion_id, producto_id))
            conn.commit()
            flash('Tarea de mantenimiento asignada correctamente.', 'success')
            return redirect(url_for('lista_mantenimientos'))
        except Exception as e:
            flash(f"Error al asignar la tarea: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('crear_mantenimiento'))

    # Método GET: Cargar productos y técnicos para los selectores del formulario
    productos = cur.execute("SELECT producto_id, nombre, numero_serie FROM productos WHERE estado_equipo_id != 3 ORDER BY nombre").fetchall()
    tecnicos = cur.execute("""
        SELECT u.usuario_id, p.primer_nombre || ' ' || p.apellido_pat as nombre_completo
        FROM usuarios u
        JOIN roles r ON u.id_rol = r.id_rol
        JOIN personas p ON u.persona_rut = p.rut
        WHERE r.nombre_rol = 'tecnico'
    """).fetchall()
    conn.close()

    return render_template('crear_mantenimiento.html', productos=productos, tecnicos=tecnicos, usuario=session.get('nombre'), permiso=session.get('permiso'), fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))
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
#app.add_url_rule('/lista_personas', 'lista_personas', placeholder_route)
app.add_url_rule('/crear_reportes', 'crear_reportes', placeholder_route)
app.add_url_rule('/lista_reportes', 'lista_reportes', placeholder_route)


# ============================================================================
# RUTA PRINCIPAL - DASHBOARD API
# ============================================================================
@app.route('/dashboard_api')
def dashboard_api():
    """Página principal con panel de control"""
    stats = db.get_stats()
    return render_template('dashboard_api.html', stats=stats, apk_exists=APK_EXISTS)

@app.route('/realtime_dashboard')
def realtime_dashboard():
    """Dashboard en tiempo real"""
    return render_template('realtime_dashboard.html')

@app.route('/history')
def history():
    """Historial de lecturas"""
    readings = db.get_all_readings(limit=50)
    return render_template('history.html', readings=readings)

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
@app.route('/api/readings')
def get_readings():
    """API para obtener lecturas (para la app móvil)"""
    try:
        limit = request.args.get('limit', 50, type=int)
        readings = db.get_all_readings(limit=limit)
        
        return jsonify({
            'success': True,
            'readings': readings,
            'total': len(readings)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error obteniendo lecturas: {str(e)}'
        }), 500

@app.route('/api/stats')
def get_stats():
    """API para obtener estadísticas"""
    try:
        stats = db.get_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error obteniendo estadísticas: {str(e)}'
        }), 500

@app.route('/api/submit-nfc', methods=['POST'])
def submit_nfc_reading():
    """API para recibir lecturas NFC desde la app móvil"""
    try:
        data = request.json
        
        # Información del dispositivo
        device_info = data.get('device_info', {})
        
        # Datos NFC
        nfc_data = data.get('nfc_data', {})
        
        # Información de la petición
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        
        # Guardar en base de datos
        reading = db.save_reading(device_info, nfc_data, ip_address, user_agent)
        
        # Emitir evento WebSocket para actualización en tiempo real
        socketio.emit('new_nfc_reading', reading)
        
        return jsonify({
            'success': True,
            'message': 'Lectura NFC guardada correctamente',
            'reading_id': reading['id']
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error procesando lectura NFC: {str(e)}'
        }), 400

@app.route('/download-app')
def download_instructions():
    """Instrucciones para descargar la app"""
    return render_template('download.html', apk_exists=APK_EXISTS)

# ============================================================================
# DESCARGA DE APK
# ============================================================================

@app.route('/download/apk')
def download_apk():
    """Descargar archivo APK"""
    if APK_EXISTS:
        return send_file(APK_FILE, as_attachment=True, 
                        download_name='NFC_Reader.apk',
                        mimetype='application/vnd.android.package-archive')
    else:
        return jsonify({
            'error': 'APK no disponible',
            'message': 'La aplicación móvil aún no ha sido compilada'
        }), 404

@app.route('/api/apk-status')
def apk_status():
    """Estado del APK"""
    return jsonify({
        'apk_exists': APK_EXISTS,
        'apk_file': APK_FILE if APK_EXISTS else None,
        'apk_size': os.path.getsize(APK_FILE) if APK_EXISTS else 0
    })

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

