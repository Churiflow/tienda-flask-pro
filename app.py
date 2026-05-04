from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# CONFIGURACIÓN
app.secret_key = 'mi_clave_secreta_pro_2026' # Necesaria para el carrito
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tienda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# MODELO DE BASE DE DATOS
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Integer, nullable=False)
    descripcion = db.Column(db.String(500))
    imagen = db.Column(db.String(500))
    categoria = db.Column(db.String(50))  # <--- ASEGÚRATE DE QUE ESTA LÍNEA ESTÉ AQUÍ

# Crear la base de datos
with app.app_context():
    db.create_all()

# --- RUTAS DE LA TIENDA ---

@app.route('/')
def home():
    # Buscador: si hay una palabra en el cuadro de búsqueda, filtra
    query = request.args.get('search')
    if query:
        productos_db = Producto.query.filter(Producto.nombre.contains(query)).all()
    else:
        productos_db = Producto.query.all()
    
    # Contamos productos en el carrito para la insignia (badge)
    cantidad_carrito = len(session.get('carrito', []))
    
    return render_template('index.html', productos=productos_db, cantidad=cantidad_carrito)

# --- SEGURIDAD: LOGIN Y LOGOUT ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        clave = request.form['clave']
        # AQUÍ DEFINES TU CLAVE
        if usuario == 'admin' and clave == '12345':
            session['admin_logueado'] = True
            return redirect(url_for('admin'))
        else:
            return "<h1>Error: Datos incorrectos</h1><a href='/login'>Reintentar</a>"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_logueado', None) # Borra el permiso de admin
    return redirect(url_for('home'))

# --- RUTA ADMIN PROTEGIDA ---

@app.route('/eliminar/<int:id>')
def eliminar(id):
    p = Producto.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('home'))

# --- RUTAS DEL CARRITO ---

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logueado'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        nuevo_p = Producto(
            nombre=request.form['nombre'],
            precio=request.form['precio'],
            descripcion=request.form['descripcion'],
            imagen=request.form['imagen'],
            categoria=request.form['categoria'] 
        )
        db.session.add(nuevo_p)
        db.session.commit()
        return redirect(url_for('admin'))
    
    # Obtenemos los datos de la DB
    productos = Producto.query.all()
    pedidos = Pedido.query.all()

    # 94. Calculamos la recaudación (con un IF por si no hay pedidos)
    total_recaudado = sum(p.total_pagado for p in pedidos) if pedidos else 0

    # 97. PASAMOS TODO AL HTML - Asegúrate de que diga exactamente esto:
    return render_template('admin.html', 
                           productos=productos, 
                           pedidos=pedidos, 
                           recaudacion=total_recaudado)

@app.route('/agregar/<int:id>')
def agregar_al_carrito(id):
    if 'carrito' not in session:
        session['carrito'] = []
    
    # Copiamos la lista, agregamos y reasignamos (importante en Flask)
    carrito = session['carrito']
    carrito.append(id)
    session['carrito'] = carrito
    return redirect(url_for('home'))

@app.route('/carrito')
def ver_carrito():
    ids_en_carrito = session.get('carrito', [])
    if not ids_en_carrito:
        return render_template('carrito.html', productos=[], total=0)
    
    # Buscamos los objetos Producto por sus IDs que están en la sesión
    productos_carrito = Producto.query.filter(Producto.id.in_(ids_en_carrito)).all()
    
    # Calculamos el total sumando el precio de cada producto encontrado
    total = sum(p.precio for p in productos_carrito)
    
    return render_template('carrito.html', productos=productos_carrito, total=total)    


@app.route('/quitar/<int:id>')
def quitar_del_carrito(id):
    if 'carrito' in session:
        carrito = session['carrito']
        if id in carrito:
            carrito.remove(id) # Quita solo una unidad del producto
            session['carrito'] = carrito
    return redirect(url_for('ver_carrito'))

@app.route('/vaciar')
def vaciar_carrito():
    session.pop('carrito', None) # Borra la lista completa
    return redirect(url_for('home'))


class Pedido(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        productos_nombres = db.Column(db.String(500)) # Lista de lo que compró
        total_pagado = db.Column(db.Integer)
        fecha = db.Column(db.DateTime, default=db.func.now())


@app.route('/finalizar_compra')
def finalizar_compra():
    # 1. Verificamos que el carrito no esté vacío
    ids_en_carrito = session.get('carrito', [])
    if not ids_en_carrito:
        return redirect(url_for('home'))
    
    # 2. Buscamos los productos para el historial
    productos_carrito = Producto.query.filter(Producto.id.in_(ids_en_carrito)).all()
    
    # 3. Creamos el resumen
    nombres_lista = [p.nombre for p in productos_carrito]
    nombres_texto = ", ".join(nombres_lista)
    total_venta = sum(p.precio for p in productos_carrito)
    
    # 4. GUARDAMOS EN LA BASE DE DATOS
    nuevo_pedido = Pedido(productos_nombres=nombres_texto, total_pagado=total_venta)
    db.session.add(nuevo_pedido)
    db.session.commit()
    
    # 5. VACIAR EL CARRITO (Limpiar la sesión)
    session.pop('carrito', None)
    
    # 6. Mostrar página de éxito
    return render_template('pago_exitoso.html', nombres=nombres_texto, total=total_venta)    


@app.route('/categoria/<nombre_cat>')
def filtrar_categoria(nombre_cat):
    # Solo buscamos los productos que coincidan con la categoría
    productos = Producto.query.filter_by(categoria=nombre_cat).all()
    return render_template('index.html', productos=productos)

# 1. FUNCIÓN PARA ELIMINAR EL PRODUCTO DEL CATÁLOGO (EL BOTÓN ROJO)
@app.route('/eliminar_producto/<int:id>')
def eliminar_producto(id):
    if not session.get('admin_logueado'):
        return redirect(url_for('login'))
    
    prod = Producto.query.get_or_404(id)
    db.session.delete(prod)
    db.session.commit()
    return redirect(url_for('admin'))

# 2. FUNCIÓN PARA DESPACHAR/BORRAR EL PEDIDO (EL BOTÓN VERDE)
@app.route('/eliminar_pedido/<int:id>')
def eliminar_pedido(id):
    if not session.get('admin_logueado'):
        return redirect(url_for('login'))
    
    ped = Pedido.query.get_or_404(id)
    db.session.delete(ped)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/imprimir_boleta/<int:id>')
def imprimir_boleta(id):
    if not session.get('admin_logueado'):
        return redirect(url_for('login'))
    
    pedido = Pedido.query.get_or_404(id)
    return render_template('boleta.html', pedido=pedido)


if __name__ == '__main__':
    app.run(debug=True, port=5000)


    
    
