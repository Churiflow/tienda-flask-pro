import os
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import csv
import io
from flask import Response
from dotenv import load_dotenv
load_dotenv()  # Carga las variables del archivo .env


# ==============================================================================
# CONFIGURACIÓN INICIAL
# ==============================================================================
app = Flask(__name__)

# Configuración de Llave Secreta
SECRET_KEY = os.environ.get('LLAVE_TIENDA')
if not SECRET_KEY:
    print("[⚠️ ALERTA DE INGENIERÍA]: No se encontró la variable 'LLAVE_TIENDA' en el entorno. Usando llave de emergencia.")
    SECRET_KEY = "clave_secreta_de_desarrollo_tiendamaster"

app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tienda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configuración de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Debes iniciar sesión para acceder a esta sección.'
login_manager.login_message_category = 'warning'

# ==============================================================================
# MODELOS DE LA BASE DE DATOS (Sin Resenas)
# ==============================================================================

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(80), unique=True, nullable=False)
    clave = db.Column(db.String(120), nullable=False)
    es_admin = db.Column(db.Boolean, default=False)

class Producto(db.Model):
    __tablename__ = 'producto'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    
    imagen = db.Column(db.Text, nullable=True, default='https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500')
    
    descripcion = db.Column(db.Text, nullable=True)
    stock = db.Column(db.Integer, default=10)

    # ⬇️ NUEVAS COLUMNAS AGREGADAS ⬇️
    categoria = db.Column(db.String(100), nullable=True)
    subcategoria = db.Column(db.String(100), nullable=True)
    genero = db.Column(db.String(50), nullable=True, default='Unisex')

class Banner(db.Model):
    __tablename__ = 'banner'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=True)
    subtitulo = db.Column(db.String(255), nullable=True)
    imagen_url = db.Column(db.Text, nullable=False)
    etiqueta = db.Column(db.String(50), nullable=True)

class Pedido(db.Model):
    __tablename__ = 'pedido'
    id = db.Column(db.Integer, primary_key=True)
    nombre_cliente = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    productos_nombres = db.Column(db.Text, nullable=False)
    total = db.Column(db.Float, nullable=False)
    estado = db.Column(db.String(50), default='Pendiente')
    fecha = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Cupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descuento = db.Column(db.Float, nullable=False)  # Porcentaje (ej: 15.0) o monto fijo
    activo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Cupon {self.codigo}>'

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# ==============================================================================
# RUTAS PÚBLICAS Y CATÁLOGO
# ==============================================================================

@app.route('/')
def index():
    productos = Producto.query.all()
    banners = Banner.query.all()  # <--- Consulta todos los banners creados
    # Calcular cantidad total de productos en el carrito para la vista
    carrito_session = session.get('carrito', {})
    cantidad = sum(carrito_session.values()) if isinstance(carrito_session, dict) else 0
    
    return render_template('index.html', productos=productos,banners=banners, cantidad=cantidad)


@app.route('/agregar_producto', methods=['POST'])
@login_required
def agregar_producto():
    nombre = request.form.get('nombre')
    precio = float(request.form.get('precio', 0))
    stock = int(request.form.get('stock', 10))
    descripcion = request.form.get('descripcion')
    imagen = request.form.get('imagen')
    categoria = request.form.get('categoria')
    subcategoria = request.form.get('subcategoria')
    genero = request.form.get('genero')

    # Si no ingresan imagen, colocar una genérica
    if not imagen or not imagen.strip():
        imagen = "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500"

    nuevo_producto = Producto(
        nombre=nombre,
        precio=precio,
        stock=stock,
        descripcion=descripcion,
        imagen=imagen.strip(),
        categoria=categoria,
        subcategoria=subcategoria,
        genero=genero
    )

    try:
        db.session.add(nuevo_producto)
        db.session.commit()
        flash('¡Producto agregado correctamente!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar el producto: {e}', 'danger')

    return redirect(url_for('admin'))


# ==============================================================================
# RUTA PARA ELIMINAR PRODUCTOS (ADMIN)
# ==============================================================================

@app.route('/eliminar_producto/<int:id>', methods=['POST', 'GET'])
@login_required
def eliminar_producto(id):
    producto = Producto.query.get_or_404(id)
    try:
        db.session.delete(producto)
        db.session.commit()
        flash(f'El producto "{producto.nombre}" ha sido eliminado con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Ocurrió un error al intentar eliminar el producto.', 'danger')
        
    return redirect(url_for('admin'))

@app.route('/producto/<int:id>')
def detalle_producto(id):
    producto = Producto.query.get_or_404(id)
    return render_template('detalle_producto.html', producto=producto)

# ==============================================================================
# RUTAS DEL CARRITO DE COMPRAS
# ==============================================================================

@app.route('/quitar_cupon')
def quitar_cupon():
    # Eliminamos las variables del cupón de la sesión
    session.pop('cupon_codigo', None)
    session.pop('porcentaje_descuento', None)
    
    flash('El cupón de descuento fue removido.', 'info')
    return redirect(url_for('carrito'))

@app.route('/carrito')
def carrito():
    # 1. Obtener los productos almacenados en la sesión
    carrito_raw = session.get('carrito', [])
    
    productos_carrito = []
    total = 0

    # 2. Iterar asegurándonos de procesar únicamente elementos válidos
    for p in carrito_raw:
        if isinstance(p, dict):
            # Obtiene el subtotal si existe, o lo calcula multiplicando precio x cantidad
            precio = p.get('precio_unitario', p.get('precio', 0))
            cantidad = p.get('cantidad', 1)
            subtotal = p.get('subtotal', precio * cantidad)
            
            total += subtotal
            productos_carrito.append(p)

    # 3. Leer la información del cupón aplicado desde la sesión
    cupon_codigo = session.get('cupon_codigo', None)
    descuento_pct = session.get('porcentaje_descuento', 0)

    # 4. Calcular el descuento en dinero y el total final
    ahorro = total * (descuento_pct / 100.0)
    total_final = max(0.0, total - ahorro)

    return render_template(
        'carrito.html',
        productos=productos_carrito,
        total=total,
        ahorro=ahorro,
        total_final=total_final,
        descuento_pct=descuento_pct,
        cupon_codigo=cupon_codigo
    )

@app.route('/agregar_al_carrito/<int:producto_id>')
def agregar_al_carrito(producto_id):
    # 1. Obtener el carrito de la sesión
    carrito = session.get('carrito', [])
    
    # Si la sesión tenía guardado un diccionario de una versión anterior, lo convertimos a lista
    if not isinstance(carrito, list):
        carrito = []
    
    # 2. Obtener el producto desde la base de datos
    producto = Producto.query.get(producto_id)
    
    if producto:
        encontrado = False
        for item in carrito:
            if isinstance(item, dict) and item.get('id') == producto_id:
                item['cantidad'] += 1
                item['subtotal'] = item['cantidad'] * item['precio_unitario']
                encontrado = True
                break
        
        if not encontrado:
            precio = producto.precio
            nuevo_item = {
                'id': producto.id,
                'nombre': producto.nombre,
                'precio_unitario': precio,
                'cantidad': 1,
                'subtotal': precio,
                'imagen': producto.imagen or ''
            }
            carrito.append(nuevo_item)
            
        session['carrito'] = carrito
        session.modified = True
        flash(f"¡{producto.nombre} añadido al carrito!", "success")
        
    return redirect(url_for('carrito'))

@app.route('/quitar_del_carrito/<int:id>')
def quitar_del_carrito(id):
    carrito_session = session.get('carrito', {})
    str_id = str(id)
    if str_id in carrito_session:
        carrito_session[str_id] -= 1
        if carrito_session[str_id] <= 0:
            del carrito_session[str_id]
        session['carrito'] = carrito_session
        flash('Cantidad actualizada en el carrito.', 'info')
    return redirect(url_for('carrito'))

@app.route('/vaciar')
def vaciar_carrito():
    session.pop('carrito', None)
    session.pop('porcentaje_descuento', None)
    flash('Carrito vaciado con éxito.', 'info')
    return redirect(url_for('carrito'))


@app.route('/aplicar_cupon', methods=['POST'])
def aplicar_cupon():
    # Toma cualquier texto ingresado, elimina espacios extra y lo pasa a mayúsculas
    codigo = request.form.get('codigo_cupon', '').strip().upper()
    
    if not codigo:
        flash('Por favor ingresa un código de descuento.', 'warning')
        return redirect(url_for('carrito'))

    # Busca en la base de datos si existe un cupón activo con el nombre exacto ingresado
    cupon = Cupon.query.filter_by(codigo=codigo, activo=True).first()
    
    if cupon:
        # Guarda el código y el porcentaje configurado en la base de datos
        session['cupon_codigo'] = cupon.codigo
        session['porcentaje_descuento'] = cupon.descuento
        flash(f'¡Cupón "{cupon.codigo}" aplicado con éxito ({cupon.descuento}% de descuento)!', 'success')
    else:
        # Si no existe en la base de datos, limpia cualquier cupón anterior
        session.pop('cupon_codigo', None)
        session.pop('porcentaje_descuento', None)
        flash('Código de descuento inválido o expirado.', 'danger')

    return redirect(url_for('carrito'))

# ==============================================================================
# RUTAS DE PAGO Y RASTREO
# ==============================================================================

@app.route('/procesar_pago_mercadopago', methods=['POST'])
def procesar_pago_mercadopago():
    carrito_session = session.get('carrito', [])
    if not carrito_session:
        flash('Tu carrito está vacío.', 'warning')
        return redirect(url_for('carrito'))

    email = request.form.get('email', 'cliente@ejemplo.com')
    nombre_titular = request.form.get('cardholderName', 'Cliente General')
    
    # Construcción de lista de productos para el historial
    nombres_prods = []
    total = 0.0

    # ⬇️ ÚNICO CAMBIO: Recorremos los elementos de la lista en lugar de usar .items()
    for item in carrito_session:
        if isinstance(item, dict):
            prod_id = item.get('id')
            cant = item.get('cantidad', 1)
            
            p = Producto.query.get(int(prod_id))
            if p:
                nombres_prods.append(f"{p.nombre} (x{cant})")
                total += p.precio * cant

    descuento_pct = session.get('porcentaje_descuento', 0)
    total_final = max(0.0, total * (1 - descuento_pct / 100.0))

    # Registro del Pedido
    nuevo_pedido = Pedido(
        nombre_cliente=nombre_titular,
        email=email,
        productos_nombres=", ".join(nombres_prods),
        total=total_final,
        estado='Pagado'
    )
    db.session.add(nuevo_pedido)
    db.session.commit()

    # Limpiar Carrito de la Sesión
    session.pop('carrito', None)
    session.pop('porcentaje_descuento', None)
    session.pop('cupon_codigo', None)

    msg_wa = f"Hola, acabo de realizar la compra #{nuevo_pedido.id} por un total de ${total_final:,.0f}."
    
    return render_template(
        'pago_exitoso.html', 
        metodo='Mercado Pago', 
        nombres=", ".join(nombres_prods),
        total=total_final, 
        mensaje=msg_wa,
        fecha=nuevo_pedido.fecha.strftime('%d/%m/%Y %H:%M')
    )

@app.route('/rastreo', methods=['GET', 'POST'])
def rastreo():
    pedido = None
    error = None
    if request.method == 'POST':
        pedido_id = request.form.get('pedido_id')
        if pedido_id and pedido_id.isdigit():
            pedido = Pedido.query.get(int(pedido_id))
            if not pedido:
                error = f"No se encontró ningún pedido con el ID #{pedido_id}."
        else:
            error = "Ingresa un número de pedido válido."
            
    return render_template('rastreo.html', pedido=pedido, error=error)

# ==============================================================================
# AUTENTICACIÓN ADMINISTRATIVA
# ==============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_input = request.form.get('usuario')
        clave_input = request.form.get('clave')
        
        user = Usuario.query.filter_by(usuario=usuario_input).first()
        if user and user.clave == clave_input:
            login_user(user)
            flash('Has iniciado sesión correctamente.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Usuario o contraseña incorrectos.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    pedidos = Pedido.query.order_by(Pedido.fecha.desc()).all()
    productos = Producto.query.all()
    banners = Banner.query.all()
    cupones = Cupon.query.all()  # <--- AGREGAR ESTA LÍNEA
    recaudacion = sum(p.total for p in pedidos if p.total)
 
    # ✅ CORRECTO: Todas las variables dentro del paréntesis de render_template
    return render_template(
        'admin.html', 
        pedidos=pedidos, 
        productos=productos, 
        banners=banners,
        cupones=cupones,         # <--- ENVIAR A LA PLANTILLA
        recaudacion=recaudacion
    )


# ==============================================================================
# INICIALIZACIÓN DE BASE DE DATOS Y EJECUCIÓN
# ==============================================================================

def inicializar_bd():
    db.create_all()
    # Crear usuario Admin de prueba si no existe
    if not Usuario.query.filter_by(usuario='admin').first():
        admin_user = Usuario(usuario='admin', clave='admin123', es_admin=True)
        db.session.add(admin_user)
        db.session.commit()
    
    # Crear productos de demostración si la base está vacía
    if Producto.query.count() == 0:
        p1 = Producto(nombre="Smartphone X Pro", precio=450000, imagen="https://via.placeholder.com/150", descripcion="Teléfono de alta gama.", stock=15)
        p2 = Producto(nombre="Audífonos Bluetooth", precio=35000, imagen="https://via.placeholder.com/150", descripcion="Cancelación de ruido activa.", stock=30)
        db.session.add_all([p1, p2])
        db.session.commit()

# ==============================================================================
# EXPORTAR LAS VENTA A EXCEL
# ==============================================================================


@app.route('/admin/exportar_ventas')
def exportar_ventas():
    # 1. Obtener todos los pedidos registrados en la base de datos
    pedidos = Pedido.query.order_by(Pedido.fecha.desc()).all()
    
    # 2. Crear un buffer en memoria para escribir el CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 3. Escribir los encabezados de las columnas
    writer.writerow(['ID Pedido', 'Cliente', 'Email', 'Total Pagado ($)', 'Fecha'])
    
    # 4. Escribir los datos de cada pedido
    for p in pedidos:
        writer.writerow([
            p.id,
            p.nombre_cliente,
            p.email,
            p.total,
            p.fecha.strftime('%Y-%m-%d %H:%M:%S') if p.fecha else ''
        ])
        
    # 5. Preparar la respuesta HTTP para descargar el archivo .csv
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            "Content-Disposition": "attachment; filename=reporte_ventas.csv"
        }
    )


# 1. Ruta para cambiar el estado del pedido desde el panel Admin
@app.route('/admin/cambiar_estado_pedido/<int:pedido_id>/<string:nuevo_estado>')
def cambiar_estado_pedido(pedido_id, nuevo_estado):
    pedido = db.session.get(Pedido, pedido_id)
    if pedido:
        pedido.estado = nuevo_estado
        db.session.commit()
        flash(f'Estado del pedido #{pedido.id} actualizado a "{nuevo_estado}".', 'success')
    else:
        flash('Pedido no encontrado.', 'danger')
    return redirect(request.referrer or url_for('admin'))


# 2. Ruta para descargar la boleta/comprobante
@app.route('/descargar_boleta/<int:pedido_id>')
def descargar_boleta(pedido_id):
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        flash('Pedido no encontrado', 'danger')
        return redirect(url_for('index'))

    # Generamos el texto formateado de la boleta
    boleta_texto = f"""========================================
         BOLETA DE COMPRA - TIENDAMASTER
========================================
N° de Pedido: #{pedido.id}
Fecha: {pedido.fecha.strftime('%Y-%m-%d %H:%M:%S') if pedido.fecha else 'N/A'}
Cliente: {pedido.nombre_cliente}
Email: {pedido.email}
Estado actual: {pedido.estado}

----------------------------------------
TOTAL PAGADO: ${pedido.total:.2f}
----------------------------------------

¡Gracias por tu compra en TiendaMaster!
========================================
"""

    return Response(
        boleta_texto,
        mimetype="text/plain",
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Disposition": f"attachment; filename=boleta_pedido_{pedido.id}.txt"
        }
    )


@app.route('/admin/banner', methods=['POST'])
def agregar_banner():
    # Asegúrate de validar que el usuario esté logueado como admin si usas autenticación
    titulo = request.form.get('titulo')
    subtitulo = request.form.get('subtitulo')
    imagen_url = request.form.get('imagen_url')
    etiqueta = request.form.get('etiqueta')

    if not imagen_url:
        flash('La URL de la imagen es obligatoria', 'danger')
        return redirect(url_for('admin'))

    nuevo_banner = Banner(
        titulo=titulo,
        subtitulo=subtitulo,
        imagen_url=imagen_url,
        etiqueta=etiqueta
    )

    db.session.add(nuevo_banner)
    db.session.commit()
    
    flash('Banner publicado con éxito', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/eliminar_banner/<int:id>')
def eliminar_banner(id):
    banner = Banner.query.get_or_404(id)
    db.session.delete(banner)
    db.session.commit()
    
    flash('Banner eliminado correctamente', 'warning')
    return redirect(url_for('admin'))



# Ruta para procesar la creación del cupón
@app.route('/admin/cupon/crear', methods=['POST'])
@login_required
def crear_cupon():
    codigo = request.form.get('codigo', '').strip().upper()
    try:
        descuento = float(request.form.get('descuento', 0))
    except ValueError:
        descuento = 0.0

    if not codigo or descuento <= 0:
        flash('Código o porcentaje de descuento inválido.', 'danger')
        return redirect(url_for('admin'))

    # Verificar si ya existe un cupón con el mismo código
    cupon_existente = Cupon.query.filter_by(codigo=codigo).first()
    if cupon_existente:
        flash('Ya existe un cupón con ese código.', 'warning')
        return redirect(url_for('admin'))

    nuevo_cupon = Cupon(codigo=codigo, descuento=descuento, activo=True)
    db.session.add(nuevo_cupon)
    db.session.commit()

    flash(f'Cupón "{codigo}" creado exitosamente.', 'success')
    return redirect(url_for('admin'))

# Ruta opcional para eliminar cupón
@app.route('/admin/cupon/eliminar/<int:id>')
@login_required
def eliminar_cupon(id):
    cupon = Cupon.query.get_or_404(id)
    db.session.delete(cupon)
    db.session.commit()
    flash('Cupón eliminado correctamente.', 'success')
    return redirect(url_for('admin'))


if __name__ == '__main__':
    with app.app_context():
        inicializar_bd()
        
    # ⬇️ app.run DEBE IR FUERA DEL CONTEXTO ⬇️
    app.run(debug=True)
    
