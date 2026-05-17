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

class Cupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False) # Ej: "OFERTA10"
    descuento = db.Column(db.Integer, nullable=False) # Porcentaje, ej: 10
    activo = db.Column(db.Boolean, default=True)


class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    productos_nombres = db.Column(db.String(500), nullable=False)
    total_pagado = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    estado = db.Column(db.String(20), default='Pendiente')

with     app.app_context():
    db.create_all()

# --- RUTAS ---
@app.route('/')
def home():
    # 1. Capturamos todos los posibles filtros desde la URL
    query = request.args.get('search')
    categoria_filtrada = request.args.get('categoria')
    subcategoria_filtrada = request.args.get('subcategoria')
    genero_filtrado = request.args.get('genero')

    # 2. Iniciamos la consulta base sobre la tabla Producto
    consulta = Producto.query

    # 3. Aplicamos los filtros acumulativos si existen
    if query:
        consulta = consulta.filter(Producto.nombre.contains(query))
    if categoria_filtrada:
        consulta = consulta.filter_by(categoria=categoria_filtrada)
    if subcategoria_filtrada:
        consulta = consulta.filter_by(subcategoria=subcategoria_filtrada)
    if genero_filtrado:
        consulta = consulta.filter_by(genero=genero_filtrado)

    # 4. Traemos los productos finales filtrados
    productos_db = consulta.all()
    
    # 5. Mantenemos tu lógica de carrito y banners intacta
    cantidad_carrito = len(session.get('carrito', []))
    banners = Banner.query.all() 
    
    return render_template('index.html', productos=productos_db, cantidad=cantidad_carrito, banners=banners)

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
    return render_template('pago_exitoso.html', nombres=nombres, total=total_final, mensaje=mensaje_wa)


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
        flash(f"¡Cupón '{codigo_ingresado}' aplicado! Descuento del {cupon.descuento}%", "success")
    else:
        session.pop('porcentaje_descuento', None) # Quitamos cualquier descuento previo
        flash("Cupón no válido o expirado", "danger")
    
    return redirect(url_for('ver_carrito'))


@app.route('/admin/crear_cupon', methods=['POST'])
def crear_cupon():
    codigo = request.form.get('codigo').upper().strip()
    descuento = int(request.form.get('descuento'))
    
    nuevo_cupon = Cupon(codigo=codigo, descuento=descuento)
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
    
    nuevo_banner = Banner(titulo=titulo, subtitulo=subtitulo, imagen_url=imagen_url)
    db.session.add(nuevo_banner)
    db.session.commit()
    
    flash("¡Banner agregado con éxito!", "success")
    return redirect(url_for('admin')) # O la ruta de tu panel

    
if __name__ == '__main__':
    app.run(debug=True, port=5000)
