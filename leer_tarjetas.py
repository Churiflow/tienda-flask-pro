from cryptography.fernet import Fernet

# El atacante consiguió la llave que estaba guardada en app.py
LLAVE_ROBADA = b'7_W2k7R_m3Uq9ZpX9f_8vB7k2M4n6Q8rTe1Y3u5I7o0='
cipher_suite = Fernet(LLAVE_ROBADA)

print("--- AUDITORÍA FORENSE DE TARJETAS ---")
print("Copia y pega el bloque cifrado largo (gAAAAAB...) que viste en el log:")
bloque_cifrado = input("> ").strip()

try:
    texto_plano = cipher_suite.decrypt(bloque_cifrado.encode('utf-8')).decode('utf-8')
    print(f"\n[🔓 ACCESO EXITOSO]: El dato real oculto es: {texto_plano}")
    print("---------------------------------------")
except Exception as e:
    print("\n[❌ ERROR]: Llave incorrecta o bloque corrupto. No se pudo descifrar.")
