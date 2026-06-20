import os
from cryptography.fernet import Fernet

# El script lee la variable desde la memoria del sistema
llave_sistema = os.environ.get('LLAVE_TIENDA')

if not llave_sistema:
    print("[❌ ERROR FORENSE]: La variable 'LLAVE_TIENDA' no está cargada en la memoria del sistema.")
    exit()

LLAVE_ROBADA = llave_sistema.encode('utf-8')
cipher_suite = Fernet(LLAVE_ROBADA)

print("--- AUDITORÍA FORENSE AVANZADA (ENVIRONMENT VARIABLES) ---")
print("Introduce el bloque cifrado (gAAAAAB...) que viste en el log:")
bloque_cifrado = input("> ").strip()

try:
    texto_plano = cipher_suite.decrypt(bloque_cifrado.encode('utf-8')).decode('utf-8')
    print(f"\n[🔓 ACCESO EXITOSO]: El dato real oculto es: {texto_plano}")
    print("---------------------------------------------------------")
except Exception as e:
    print("\n[❌ ERROR]: Bloque corrupto o manipulación detectada.")
