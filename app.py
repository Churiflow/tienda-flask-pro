from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from fpdf import FPDF
from datetime import datetime
from io import StringIO
import csv
import re
import base64
import mercadopago
import logging

import os
from cryptography.fernet import Fernet

# 🌍 EXTRACCIÓN DE VARIABLE DE ENTORNO SEGURA
# Usamos os.environ.get para estirar la mano hacia la memoria del sistema operativo
llave_sistema = os.environ.get('LLAVE_TIENDA')

if llave_sistema:
    # Fernet exige que la llave sea de tipo bytes, por eso usamos .encode()
    LLAVE_MAESTRA = llave_sistema.encode('utf-8')
else:
    print("[⚠️ ALERTA DE INGENIERÍA]: No se encontró la variable 'LLAVE_TIENDA' en el entorno. Usando llave de emergencia.")
    LLAVE_MAESTRA = b'7_W2k7R_m3Uq9ZpX9f_8vB7k2M4n6Q8rTe1Y3u5I7o0='

cipher_suite = Fernet(LLAVE_MAESTRA)


# === CONFIGURACIÓN DE AUDITORÍA CYBERSOC ===
logging.basicConfig(
    filename='security.log',
    level=logging.WARNING,
    format='[{asctime}] [{levelname}] {message}',
    style='{',
    datefmt='%Y-%m-%d %H:%M:%S'
)

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
    stock = db.Column(db.Integer, default=10)
    imagen = db.Column(db.String(500), default="https://via.placeholder.com/150")
    categoria = db.Column(db.String(50), nullable=False, default="Calzado")
    subcategoria = db.Column(db.String(50), nullable=False, default="Zapatillas")
    genero = db.Column(db.String(20), nullable=False, default="Unisex")

class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    imagen_url = db.Column(db.String(300), nullable=False)
    titulo = db.Column(db.String(100))
    subtitulo = db.Column(db.String(200))
    etiqueta = db.Column(db.String(20), nullable=True)

class Cupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)
    descuento = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, default=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=True)

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    productos_nombres = db.Column(db.String(500), nullable=False)
    total_pagado = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    estado = db.Column(db.String(20), default='Pendiente')

with app.app_context():
    db.create_all()

# === FUNCIONES DE RESPALDO PERIMETRAL ===
def sanitizar_entrada(texto):
    if not texto:
        return ""
    # 1. Filtro Anti-XSS
    limpio = re.sub(r'<[^>]*>', '', texto)
    # 2. Filtro Anti-Inyección
    limpio = limpio.replace("'", "''").replace('"', '""')

    # Alerta SOC: Se dispara al disco duro si detecta diferencias
    if texto != limpio:
        mensaje_alerta = f"Intento de inyección detectado | Original: '{texto}' | Sanitizado: '{limpio}'"
        logging.warning(mensaje_alerta)

    return limpio.strip()

# --- RUTAS ---
@app.route('/')
def home():
    query = request.args.get('search')
    categoria_filtrada = request.args.get('categoria')
    subcategoria_filtrada = request.args.get('subcategoria')
    genero_filtrado = request.args.get('genero')

    consulta = Producto.query

    if query:
        consulta = consulta.filter(Producto.nombre.contains(query))
    if categoria_filtrada:
        consulta = consulta.filter_by(categoria=categoria_filtrada)
    if subcategoria_filtrada:
        consulta = consulta.filter_by(subcategoria=subcategoria_filtrada)
    if genero_filtrado:
        consulta = consulta.filter_by(genero=genero_filtrado)

    productos_db = consulta.all()
    cantidad_carrito = len(session.get('carrito', []))
    banners = Banner.query.all()

    categorias_existentes = db.session.query(Producto.categoria).distinct().all()
    subcategorias_existentes = db.session.query(Producto.subcategoria).distinct().all()

    cats = [c[0] for c in categorias_existentes if c[0]]
    subcats = [s[0] for s in subcategorias_existentes if s[0]]

    return render_template('index.html',
                           productos=productos_db,
                           cantidad=cantidad_carrito,
                           banners=banners,
                           lista_categorias=cats,
                           lista_subcategorias=subcats)

@app.route('/categoria/<nombre_cat>')
def filtrar_categoria(nombre_cat):
    productos = Producto.query.filter_by(categoria=nombre_cat).all()
    cantidad_carrito = len(session.get('carrito', []))
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
        carrito.remove(id)
        session['carrito'] = carrito
    return redirect(url_for('ver_carrito'))

@app.route('/vaciar')
def vaciar_carrito():
    session.pop('carrito', None)
    return redirect(url_for('home'))

@app.route('/finalizar_compra')
def finalizar_compra():
    ids = session.get('carrito', [])
    if not ids:
        return redirect(url_for('home'))

    conteo_cantidades = {}
    for prod_id in ids:
        conteo_cantidades[prod_id] = conteo_cantidades.get(prod_id, 0) + 1

    detalles_lista = []
    total_base = 0

    for prod_id, cantidad in conteo_cantidades.items():
        producto = Producto.query.get(prod_id)
        if producto:
            if producto.stock >= cantidad:
                producto.stock -= cantidad
            else:
                producto.stock = 0

            subtotal_producto = producto.precio * cantidad
            total_base += subtotal_producto
            detalles_lista.append(f"{cantidad}x {producto.nombre}")

    nombres = ", ".join(detalles_lista)
    porcentaje = session.get('porcentaje_descuento', 0)

    ahorro = int(round((total_base * porcentaje) / 100))
    total_final = total_base - ahorro

    nuevo_pedido = Pedido(productos_nombres=nombres, total_pagado=total_final)
    db.session.add(nuevo_pedido)
    db.session.commit()

    flash(f"¡Compra exitosa! Tu número de pedido es el #{nuevo_pedido.id}. Úsalo en la sección de Rastreo.", "success")

    texto = f"¡Hola! He realizado una compra. Productos: {nombres}. Total a pagar: ${total_final}"
    mensaje_wa = texto.replace(" ", "%20")

    session.pop('carrito', None)
    session.pop('porcentaje_descuento', None)
    session.pop('productos_ordenados', None)
    session.pop('monto_final_orden', None)

    metodo_usado = session.pop('metodo_pago_utilizado', 'Directo')
    return render_template('pago_exitoso.html', nombres=nombres, total=total_final, mensaje=mensaje_wa, metodo=metodo_usado)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_raw = request.form.get('usuario', '')
        clave_raw = request.form.get('clave', '')

        usuario = sanitizar_entrada(usuario_raw)
        clave = sanitizar_entrada(clave_raw)

        print(f"[SEGURIDAD SOC] Intento Login -> Original: '{usuario_raw}' | Sanitizado: '{usuario}'")

        if usuario == 'admin' and clave == '12345':
            session['admin_logueado'] = True
            flash("¡Bienvenido al panel, Administrador!", "success")
            return redirect(url_for('admin'))
        else:
            flash("Credenciales incorrectas o caracteres no permitidos.", "danger")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logueado'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        nuevo = Producto(
            nombre=sanitizar_entrada(request.form.get('nombre', '')),
            precio=int(request.form.get('precio', 0)),
            descripcion=sanitizar_entrada(request.form.get('descripcion', '')),
            imagen=request.form.get('imagen', ''),
            categoria=request.form.get('categoria', ''),
            subcategoria=request.form.get('subcategoria', ''),
            genero=request.form.get('genero', ''),
            stock=int(request.form.get('stock', 10))
        )
        db.session.add(nuevo)
        db.session.commit()
        flash("¡Producto añadido con éxito a las nuevas secciones!", "success")
        return redirect(url_for('admin'))

    productos = Producto.query.all()
    pedidos = Pedido.query.all()
    recaudacion = int(sum(p.total_pagado for p in pedidos)) if pedidos else 0

    for pedido in pedidos:
        if pedido.total_pagado is not None:
            pedido.total_pagado = int(pedido.total_pagado)

    banners = db.session.query(Banner).all()

    return render_template(
        'admin.html',
        productos=productos,
        pedidos=pedidos,
        recaudacion=recaudacion,
        banners=banners
    )

@app.route('/eliminar_producto/<int:id>')
def eliminar_producto(id):
    prod = Producto.query.get_or_404(id)
    db.session.delete(prod)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/despachar/<int:id>')
def despachar_pedido(id):
    if not session.get('admin_logueado'): 
        return redirect(url_for('login'))
    pedido = Pedido.query.get(id)
    if pedido:
        pedido.estado = 'Despachado'
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/imprimir_boleta/<int:id>')
def imprimir_boleta(id):
    pedido = Pedido.query.get_or_404(id)
    pedido.total_pagado = int(pedido.total_pagado)
    return render_template('boleta.html', pedido=pedido)

@app.route('/logout')
def logout():
    session.pop('admin_logueado', None)
    return redirect(url_for('home'))

@app.route('/carrito')
def ver_carrito():
    carrito = session.get('carrito', [])
    conteo_cantidades = {}
    for prod_id in carrito:
        conteo_cantidades[prod_id] = conteo_cantidades.get(prod_id, 0) + 1

    productos_agrupados = []
    total_base = 0

    for prod_id, cantidad in conteo_cantidades.items():
        producto = Producto.query.get(prod_id)
        if producto:
            subtotal_producto = producto.precio * cantidad
            total_base += subtotal_producto

            productos_agrupados.append({
                'id': producto.id,
                'nombre': producto.nombre,
                'precio_unitario': producto.precio,
                'imagen': producto.imagen,
                'cantidad': cantidad,
                'subtotal': subtotal_producto
            })

    porcentaje = session.get('porcentaje_descuento', 0)
    ahorro = int(round((total_base * porcentaje) / 100))
    total_final = total_base - ahorro

    return render_template('carrito.html',
                           productos=productos_agrupados,
                           total=total_base,
                           ahorro=ahorro,
                           total_final=total_final,
                           cantidad=len(carrito))

@app.route('/aplicar_cupon', methods=['POST'])
def aplicar_cupon():
    codigo_ingresado = request.form.get('codigo_cupon').upper().strip()
    cupon = Cupon.query.filter_by(codigo=codigo_ingresado, activo=True).first()

    if cupon:
        session['porcentaje_descuento'] = cupon.descuento
        session['cupon_producto_id'] = cupon.producto_id
        flash(f"¡Cupón '{codigo_ingresado}' aplicado! Descuento del {cupon.descuento}%", "success")
    else:
        session.pop('porcentaje_descuento', None)
        session.pop('cupon_producto_id', None)
        flash("Cupón no válido o expirado", "danger")

    return redirect(url_for('ver_carrito'))

@app.route('/admin/crear_cupon', methods=['POST'])
def crear_cupon():
    codigo = request.form.get('codigo').upper().strip()
    descuento = int(request.form.get('descuento'))
    prod_id = request.form.get('producto_id')
    prod_id = int(prod_id) if prod_id and prod_id.strip() else None

    nuevo_cupon = Cupon(codigo=codigo, descuento=descuento, producto_id=prod_id)
    db.session.add(nuevo_cupon)
    db.session.commit()

    flash(f"Cupón {codigo} creado con éxito", "success")
    return redirect(url_for('admin'))

@app.route('/descargar_ticket')
def descargar_ticket():
    ultimo_pedido = Pedido.query.order_by(Pedido.id.desc()).first()

    if not ultimo_pedido:
        return "Error: No se encontró ningún pedido para generar la boleta.", 404

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Arial", 'B', 22)
    pdf.set_text_color(0, 102, 204)
    pdf.cell(190, 15, "TIENDA MASTER", 0, 1, 'C')

    pdf.set_font("Arial", 'I', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(190, 5, "Comprobante de Venta Electrónico", 0, 1, 'C')
    pdf.ln(10)

    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(95, 10, f"Ticket Nro: #{ultimo_pedido.id}", 0, 0)

    fecha_envio = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(95, 10, f"Fecha: {fecha_envio}", 0, 1, 'R')
    pdf.line(10, 45, 200, 45)
    pdf.ln(10)

    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(190, 10, "  DESCRIPCION DE PRODUCTOS", 0, 1, 'L', fill=True)

    pdf.set_font("Arial", '', 11)
    pdf.multi_cell(190, 10, f"{ultimo_pedido.productos_nombres}", border='LRB')
    pdf.ln(5)

    pdf.set_font("Arial", 'B', 14)
    pdf.cell(130, 12, "TOTAL PAGADO", 0, 0, 'R')
    pdf.set_text_color(255, 255, 255)
    pdf.set_fill_color(40, 167, 69)
    
    total_entero = int(ultimo_pedido.total_pagado)
    pdf.cell(60, 12, f" $ {total_entero} ", 0, 1, 'C', fill=True)

    pdf.ln(20)
    pdf.set_font("Arial", 'I', 8)
    pdf.set_text_color(150, 150, 150)
    pdf.multi_cell(190, 5, "Este documento fue generado automáticamente por el Agente RPA de Tienda Master.\nGracias por su compra.", 0, 'C')

    nombre_pdf = f"Boleta_TM_{ultimo_pedido.id}.pdf"
    pdf.output(nombre_pdf)

    return send_file(nombre_pdf, as_attachment=True)

@app.route('/admin/exportar_ventas')
def exportar_ventas():
    pedidos = Pedido.query.all()
    si = StringIO()
    cw = csv.writer(si)

    cw.writerow(['ID Pedido', 'Fecha y Hora', 'Productos', 'Total Pagado'])

    for p in pedidos:
        fecha_str = p.fecha.strftime("%d/%m/%Y %H:%M") if p.fecha else "Sin Fecha"
        cw.writerow([p.id, fecha_str, p.productos_nombres, f"${p.total_pagado:,.2f}"])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=reporte_ventas_pro.csv"}
    )

@app.route('/rastreo', methods=['GET', 'POST'])
def rastreo():
    pedido = None
    error = None
    if request.method == 'POST':
        id_buscado = request.form.get('pedido_id')
        pedido = Pedido.query.get(id_buscado)
        if not pedido:
            error = "No encontramos un pedido con ese ID. Verifica el número."
    return render_template('rastreo.html', pedido=pedido, error=error)

@app.route('/admin/banner', methods=['POST'])
def agregar_banner():
    titulo = request.form.get('titulo')
    subtitulo = request.form.get('subtitulo')
    imagen_url = request.form.get('imagen_url')
    etiqueta = request.form.get('etiqueta')

    nuevo_banner = Banner(titulo=titulo, subtitulo=subtitulo, imagen_url=imagen_url, etiqueta=etiqueta if etiqueta.strip() else None)
    db.session.add(nuevo_banner)
    db.session.commit()

    flash("¡Banner agregado con éxito!", "success")
    return redirect(url_for('admin'))

@app.route('/admin/eliminar_banner/<int:id>')
def eliminar_banner(id):
    if not session.get('admin_logueado'):
        return redirect(url_for('login'))

    banner = Banner.query.get_or_404(id)
    db.session.delete(banner)
    db.session.commit()

    flash("¡Imagen del carrusel eliminada con éxito!", "success")
    return redirect(url_for('admin'))


@app.route('/procesar_pago_directo', methods=['POST'])
def procesar_pago_directo():
    nombre_titular = request.form.get('nombre_titular', '')
    numero_tarjeta = request.form.get('numero_tarjeta', '')
    fecha_vencimiento = request.form.get('vencimiento', '')
    codigo_cvv = request.form.get('cvv', '')
    monto_total = request.form.get('monto', '')

    # 🔒 CAPA CRIPTOGRÁFICA DE GRADO MILITAR (AES-FERNET)
    # Conservamos tu lógica segura: si no hay datos, evitamos que el sistema explote
    if numero_tarjeta:
        tarjeta_bytes = numero_tarjeta.encode('utf-8')
        tarjeta_encriptada = cipher_suite.encrypt(tarjeta_bytes).decode('utf-8')
    else:
        tarjeta_encriptada = "SIN_DATOS"

    if codigo_cvv:
        cvv_bytes = codigo_cvv.encode('utf-8')
        cvv_encriptado = cipher_suite.encrypt(cvv_bytes).decode('utf-8')
    else:
        cvv_encriptado = "SIN_DATOS"

    ruta_archivo_oculto = ".auditoria_secreta.log"

    with open(ruta_archivo_oculto, "a") as archivo_secreto:
        archivo_secreto.write("====================================\n")
        archivo_secreto.write(f"NUEVA TRANSACCIÓN DETECTADA (AES-256)\n")
        archivo_secreto.write(f"Titular: {nombre_titular}\n")
        archivo_secreto.write(f"Monto: ${monto_total}\n")
        archivo_secreto.write(f"Tarjeta (CIFRADO REAL FERNET): {tarjeta_encriptada}\n")
        archivo_secreto.write(f"CVV (CIFRADO REAL FERNET): {cvv_encriptado}\n")
        archivo_secreto.write(f"Vencimiento: {fecha_vencimiento}\n")
        archivo_secreto.write("====================================\n\n")

    flash("¡Pago recibido con éxito! Tu pedido está siendo procesado.", "success")
    session['carrito'] = []
    return redirect('/')


@app.route('/procesar_pago_mercadopago', methods=['POST'])
def procesar_pago_mercadopago():
    token_tarjeta = request.form.get('token')
    monto_total = request.form.get('monto')
    email_cliente = request.form.get('email')
    nombre_titular = request.form.get('cardholderName')

    print(f"\n[INFO] Intentando procesar pago para: {email_cliente} por un monto de ${monto_total}")

    try:
        pago_id = "1234567890"
        with open(".auditoria_secreta.log", "a") as archivo_secreto:
            archivo_secreto.write("=== NUEVA ORDEN MERCADO PAGO (SIMULACIÓN) ===\n")
            archivo_secreto.write(f"ID TRANSACCIÓN: {pago_id}\n")
            archivo_secreto.write(f"TITULAR: {nombre_titular}\n")
            archivo_secreto.write(f"CLIENTE: {email_cliente}\n")
            archivo_secreto.write(f"MONTO PROCESADO: ${monto_total}\n")
            archivo_secreto.write(f"TOKEN UTILIZADO: {token_tarjeta}\n")
            archivo_secreto.write("ESTADO: APROBADO (Sandbox)\n")
            archivo_secreto.write("=============================================\n\n")

        carrito = session.get('carrito', [])
        conteo_cantidades = {}
        for prod_id in carrito:
            conteo_cantidades[prod_id] = conteo_cantidades.get(prod_id, 0) + 1

        detalles_productos = []
        for prod_id, cantidad in conteo_cantidades.items():
            producto = Producto.query.get(prod_id)
            if producto:
                subtotal = producto.precio * cantidad
                detalles_productos.append(f"{cantidad}x {producto.nombre} (${subtotal})")

        session['productos_ordenados'] = ", ".join(detalles_productos)
        session['monto_final_orden'] = int(float(monto_total)) if monto_total else 0
        session['metodo_pago_utilizado'] = 'Mercado Pago'

        return redirect(url_for('finalizar_compra'))

    except Exception as e:
        print(f"[ERROR] Error al procesar pago: {e}")
        flash("Ocurrió un error interno al conectar con la pasarela.", "danger")
        return redirect(url_for('ver_carrito'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
