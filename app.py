from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'mi_clave_secreta_pro_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tienda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS ---
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Integer, nullable=False)
    descripcion = db.Column(db.String(500))
    imagen = db.Column(db.String(500))
    categoria = db.Column(db.String(50))
    stock = db.Column(db.Integer, default=10)

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    productos_nombres = db.Column(db.String(500))
    total_pagado = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=db.func.now())

with app.app_context():
    db.create_all()

# --- RUTAS ---
@app.route('/')
def home():
    query = request.args.get('search')
    productos_db = Producto.query.filter(Producto.nombre.contains(query)).all() if query else Producto.query.all()
    cantidad_carrito = len(session.get('carrito', []))
    return render_template('index.html', productos=productos_db, cantidad=cantidad_carrito)


@app.route('/categoria/<nombre_cat>')
def filtrar_categoria(nombre_cat):
    # 1. Buscamos los productos que coincidan con la categoría
    productos = Producto.query.filter_by(categoria=nombre_cat).all()
        
    # 2. Calculamos la cantidad para el icono del carrito
    cantidad_carrito = len(session.get('carrito', []))
    
    # 3. Reutilizamos index.html para mostrar los resultados
    return render_template('index.html', productos=productos, cantidad=cantidad_carrito)


@app.route('/agregar/<int:id>')
def agregar_al_carrito(id):
    prod = Producto.query.get_or_404(id)
    if prod.stock > 0:
        carrito = session.get('carrito', [])
        carrito.append(id)
        session['carrito'] = carrito
    return redirect(url_for('home'))


@app.route('/quitar/<int:id>')
def quitar_del_carrito(id):
    carrito = session.get('carrito', [])
    if id in carrito:
        carrito.remove(id) # Quita solo una unidad
        session['carrito'] = carrito
    return redirect(url_for('ver_carrito'))

@app.route('/vaciar')
def vaciar_carrito():
    session.pop('carrito', None)
    return redirect(url_for('home'))

@app.route('/finalizar_compra')
def finalizar_compra():
    ids = session.get('carrito', [])
    if not ids: return redirect(url_for('home'))

    # 1. Buscamos los productos (Tu lógica actual)
    productos_obj = Producto.query.filter(Producto.id.in_(ids)).all()
    
    # 2. Descontar stock (Tu lógica actual)
    for p in productos_obj:
        if p.stock > 0:
            p.stock -= 1

    # 3. Preparar datos para el pedido (Tu lógica actual)
    nombres = ", ".join([p.nombre for p in productos_obj])
    total = sum(p.precio for p in productos_obj)

    # 4. Guardar en la base de datos (Tu lógica actual)
    nuevo_pedido = Pedido(productos_nombres=nombres, total_pagado=total)
    db.session.add(nuevo_pedido)
    db.session.commit()
    # --- AQUÍ EMPIEZA LO NUEVO SIN BORRAR LO ANTERIOR ---

    # 5. Creamos el mensaje para WhatsApp
    # Usamos .replace(" ", "%20") porque los links no aceptan espacios en blanco
    texto = f"¡Hola! He realizado una compra. Productos: {nombres}. Total a pagar: ${total}"
    mensaje_wa = texto.replace(" ", "%20")

    # 6. Limpiamos el carrito (Tu lógica actual)
    session.pop('carrito', None)

    # 7. Enviamos TODO a la página de éxito, incluyendo el nuevo 'mensaje'
    return render_template('pago_exitoso.html', nombres=nombres, total=total, mensaje=mensaje_wa)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['usuario'] == 'admin' and request.form['clave'] == '12345':
            session['admin_logueado'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logueado'): return redirect(url_for('login'))
    if request.method == 'POST':
        nuevo = Producto(
            nombre=request.form['nombre'],
            precio=int(request.form['precio']),
            descripcion=request.form['descripcion'],
            imagen=request.form['imagen'],
            categoria=request.form['categoria'],
            stock=int(request.form.get('stock', 10))
        )
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for('admin'))
    
    productos = Producto.query.all()
    pedidos = Pedido.query.all()
    recaudacion = sum(p.total_pagado for p in pedidos) if pedidos else 0
    return render_template('admin.html', productos=productos, pedidos=pedidos, recaudacion=recaudacion)

@app.route('/eliminar_producto/<int:id>')
def eliminar_producto(id):
    prod = Producto.query.get_or_404(id)
    db.session.delete(prod)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/eliminar_pedido/<int:id>')
def eliminar_pedido(id):
    ped = Pedido.query.get_or_404(id)
    db.session.delete(ped)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/imprimir_boleta/<int:id>')
def imprimir_boleta(id):
    pedido = Pedido.query.get_or_404(id)
    return render_template('boleta.html', pedido=pedido)

@app.route('/logout')
def logout():
    session.pop('admin_logueado', None)
    return redirect(url_for('home'))

@app.route('/carrito')
def ver_carrito():
    ids = session.get('carrito', [])
    productos_carrito = Producto.query.filter(Producto.id.in_(ids)).all()
    total = sum(p.precio for p in productos_carrito)
    return render_template('carrito.html', productos=productos_carrito, total=total)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
