import os
import io
import re
import random
import string
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF
import mercadopago

# Configuración de logs para producción
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# --- CONFIGURACIÓN PARA RENDER Y PRODUCCIÓN ---
app.secret_key = os.environ.get('SECRET_KEY', 'clave_desarrollo_temporal_12345')

# Configuración de SQLite/PostgreSQL dinámica para Render
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///tienda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configuración de Mercado Pago
MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN', 'APP_USR-7539402517036660-022018-090bc66f643fdb88b22e1189bcdd9ed1-228392131')
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)


# --- MODELOS DE LA BASE DE DATOS ---
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Integer, nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    categoria = db.Column(db.String(50), nullable=False)      # Ejemplo: Calzado, Ropa, Accesorios
    subcategoria = db.Column(db.String(50), nullable=False)   # Ejemplo: Zapatillas, Botas, Poleras
    genero = db.Column(db.String(20), nullable=False)         # Hombre, Mujer, Unisex, Niños
    imagen_url = db.Column(db.String(300), nullable=True)     # URL de imagen externa
    stock = db.Column(db.Integer, default=10)


class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo_ticket = db.Column(db.String(20), unique=True, nullable=False)
    titular = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    rut = db.Column(db.String(20), nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)
    monto_total = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    detalles = db.Column(db.Text, nullable=False) # Guardamos un resumen en texto de los productos


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)


# --- INICIALIZACIÓN DE BASE DE DATOS Y DATOS DEMO ---
with app.app_context():
    db.create_all()
    # Si la base de datos está vacía en Render, crea un producto base para evitar errores 500
    if not Producto.query.first():
        prod_demo = Producto(
            nombre="Zapatilla Demo Pro",
            precio=29990,
            descripcion="Producto de demostración inicial.",
            categoria="Calzado",
            subcategoria="Zapatillas",
            genero="Unisex",
            imagen_url="https://via.placeholder.com/300",
            stock=10
        )
        db.session.add(prod_demo)
        db.session.commit()


# --- RUTAS PRINCIPALES DE LA TIENDA ---
@app.route('/')
def index():
    cat = request.args.get('categoria')
    subcat = request.args.get('subcategoria')
    gen = request.args.get('genero')

    query = Producto.query

    if cat:
        query = query.filter_by(categoria=cat)
    if subcat:
        query = query.filter_by(subcategoria=subcat)
    if gen:
        query = query.filter_by(genero=gen)

    productos = query.all()

    categorias_existentes = db.session.query(Producto.categoria).distinct().all()
    categorias_existentes = [c[0] for c in categorias_existentes if c[0]]

    subcategorias_existentes = db.session.query(Producto.subcategoria).distinct().all()
    subcategorias_existentes = [s[0] for s in subcategorias_existentes if s[0]]

    return render_template(
        'index.html', 
        productos=productos, 
        categorias=categorias_existentes,
        subcategorias=subcategorias_existentes,
        cat_actual=cat,
        subcat_actual=subcat,
        gen_actual=gen
    )


@app.route('/producto/<int:id>')
def detalle_producto(id):
    producto = Producto.query.get_or_404(id)
    return render_template('detalle.html', producto=producto)


# --- RUTA DE ADMINISTRACIÓN ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'login':
            username = request.form.get('username')
            password = request.form.get('password')
            user = Usuario.query.filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                session['admin_logged'] = True
                flash('Sesión iniciada correctamente.', 'success')
            else:
                flash('Usuario o contraseña incorrectos.', 'danger')
            return redirect(url_for('admin'))

        if action == 'logout':
            session.pop('admin_logged', None)
            flash('Sesión cerrada.', 'info')
            return redirect(url_for('admin'))

        if not session.get('admin_logged'):
            flash('Acceso no autorizado.', 'danger')
            return redirect(url_for('admin'))

        if action == 'crear':
            nuevo = Producto(
                nombre=request.form.get('nombre'),
                precio=int(request.form.get('precio', 0)),
                descripcion=request.form.get('descripcion'),
                categoria=request.form.get('categoria'),
                subcategoria=request.form.get('subcategoria'),
                genero=request.form.get('genero'),
                imagen_url=request.form.get('imagen_url'),
                stock=int(request.form.get('stock', 10))
            )
            db.session.add(nuevo)
            db.session.commit()
            flash('Producto agregado con éxito.', 'success')

        elif action == 'editar':
            p = Producto.query.get(request.form.get('id'))
            if p:
                p.nombre = request.form.get('nombre')
                p.precio = int(request.form.get('precio', 0))
                p.descripcion = request.form.get('descripcion')
                p.categoria = request.form.get('categoria')
                p.subcategoria = request.form.get('subcategoria')
                p.genero = request.form.get('genero')
                p.imagen_url = request.form.get('imagen_url')
                p.stock = int(request.form.get('stock', 0))
                db.session.commit()
                flash('Producto actualizado.', 'success')

        elif action == 'eliminar':
            p = Producto.query.get(request.form.get('id'))
            if p:
                db.session.delete(p)
                db.session.commit()
                flash('Producto eliminado.', 'warning')

        return redirect(url_for('admin'))

    productos = Producto.query.all() if session.get('admin_logged') else []
    ventas = Venta.query.order_by(Venta.fecha.desc()).all() if session.get('admin_logged') else []
    return render_template('admin.html', productos=productos, ventas=ventas)


# --- PROCESAMIENTO DE PAGOS ---
@app.route('/procesar_pago_directo', methods=['POST'])
def procesar_pago_directo():
    datos = request.json
    cart = datos.get('cart', [])
    
    if not cart:
        return jsonify({'success': False, 'message': 'El carrito está vacío'}), 400

    nombre_titular = datos.get('nombre_titular', 'Cliente Directo')
    email = datos.get('email', 'cliente@correo.com')
    rut = datos.get('rut', '11111111-1')
    metodo = datos.get('metodo', 'Tarjeta de Crédito Directa')

    monto_total = 0
    detalles_items = []

    for item in cart:
        prod = Producto.query.get(item['id'])
        if prod:
            subtotal = prod.precio * item['cantidad']
            monto_total += subtotal
            detalles_items.append(f"{prod.nombre} x{item['cantidad']} (${subtotal})")

    # Registro en log interno en lugar de archivo físico en disco
    logging.info(f"TRANSACCIÓN DIRECTA - Titular: {nombre_titular} | RUT: {rut} | Monto: ${monto_total}")

    codigo_ticket = 'TK-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    nueva_venta = Venta(
        codigo_ticket=codigo_ticket,
        titular=nombre_titular,
        email=email,
        rut=rut,
        metodo_pago=metodo,
        monto_total=monto_total,
        detalles=", ".join(detalles_items)
    )

    db.session.add(nueva_venta)
    db.session.commit()

    return jsonify({'success': True, 'ticket_code': codigo_ticket})


@app.route('/procesar_pago_mercadopago', methods=['POST'])
def procesar_pago_mercadopago():
    datos = request.json
    cart = datos.get('cart', [])

    if not cart:
        return jsonify({'success': False, 'message': 'El carrito está vacío'}), 400

    nombre_titular = datos.get('nombre_titular', 'Cliente MP')
    email = datos.get('email', 'cliente_mp@correo.com')
    rut = datos.get('rut', '22222222-2')

    items_mp = []
    monto_total = 0
    detalles_items = []

    for item in cart:
        prod = Producto.query.get(item['id'])
        if prod:
            subtotal = prod.precio * item['cantidad']
            monto_total += subtotal
            detalles_items.append(f"{prod.nombre} x{item['cantidad']} (${subtotal})")
            items_mp.append({
                "title": prod.nombre,
                "quantity": int(item['cantidad']),
                "currency_id": "CLP",
                "unit_price": float(prod.precio)
            })

    logging.info(f"TRANSACCIÓN MERCADO PAGO - Titular: {nombre_titular} | RUT: {rut} | Monto: ${monto_total}")

    codigo_ticket = 'TK-MP-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    nueva_venta = Venta(
        codigo_ticket=codigo_ticket,
        titular=nombre_titular,
        email=email,
        rut=rut,
        metodo_pago='Mercado Pago',
        monto_total=monto_total,
        detalles=", ".join(detalles_items)
    )
    db.session.add(nueva_venta)
    db.session.commit()

    preference_data = {
        "items": items_mp,
        "payer": {
            "name": nombre_titular,
            "email": email
        },
        "back_urls": {
            "success": url_for('index', _external=True) + f"?ticket={codigo_ticket}",
            "failure": url_for('index', _external=True),
            "pending": url_for('index', _external=True)
        },
        "auto_return": "approved"
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        return jsonify({
            'success': True, 
            'init_point': preference["init_point"], 
            'ticket_code': codigo_ticket
        })
    except Exception as e:
        logging.error(f"Error al crear preferencia de Mercado Pago: {str(e)}")
        return jsonify({'success': False, 'message': 'Error al conectar con Mercado Pago'}), 500


# --- GENERACIÓN Y DESCARGA DEL TICKET PDF ---
@app.route('/descargar_ticket/<codigo>')
def descargar_ticket(codigo):
    venta = Venta.query.filter_by(codigo_ticket=codigo).first_or_404()

    pdf = FPDF()
    pdf.add_page()
    
    # Encabezado del comprobante
    # Nota: Se utiliza 'Helvetica' por compatibilidad completa en fpdf2 dentro de Linux/Render
    pdf.set_font("Helvetica", 'B', 22)
    pdf.cell(0, 15, "TICKET DE COMPRA", ln=True, align='C')
    pdf.set_font("Helvetica", '', 12)
    pdf.cell(0, 10, f"Codigo de Venta: {venta.codigo_ticket}", ln=True, align='C')
    pdf.ln(10)

    # Datos del Cliente
    pdf.set_font("Helvetica", 'B', 14)
    pdf.cell(0, 10, "Detalles del Cliente", ln=True)
    pdf.set_font("Helvetica", '', 12)
    pdf.cell(0, 8, f"Titular: {venta.titular}", ln=True)
    pdf.cell(0, 8, f"RUT: {venta.rut}", ln=True)
    pdf.cell(0, 8, f"Email: {venta.email}", ln=True)
    pdf.cell(0, 8, f"Metodo de Pago: {venta.metodo_pago}", ln=True)
    pdf.cell(0, 8, f"Fecha: {venta.fecha.strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
    pdf.ln(10)

    # Resumen del Pedido
    pdf.set_font("Helvetica", 'B', 14)
    pdf.cell(0, 10, "Resumen de Productos", ln=True)
    pdf.set_font("Helvetica", '', 12)
    
    items = venta.detalles.split(", ")
    for item in items:
        pdf.cell(0, 8, f"- {item}", ln=True)

    pdf.ln(10)
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(0, 10, f"TOTAL PAGADO: ${venta.monto_total}", ln=True, align='R')

    pdf_buffer = io.BytesIO()
    pdf_output = pdf.output()
    pdf_buffer.write(pdf_output)
    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"Ticket_{venta.codigo_ticket}.pdf",
        mimetype='application/pdf'
    )


if __name__ == '__main__':
    app.run(debug=True)
