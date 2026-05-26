import base64

print("\n=== AUDITORÍA PRIVADA: REGISTROS DESENCRIPTADOS ===")
try:
    with open(".auditoria_secreta.log", "r") as archivo:
        for linea in archivo:
            if "Tarjeta (Encriptada en Base64):" in linea:
                encriptado = linea.split(": ")[1].strip()
                desencriptado = base64.b64decode(encriptado).decode('utf-8')
                print(f"-> Número de Tarjeta Real: {desencriptado}")
            elif "CVV (Encriptado en Base64):" in linea:
                encriptado = linea.split(": ")[1].strip()
                desencriptado = base64.b64decode(encriptado).decode('utf-8')
                print(f"-> Código CVV Real: {desencriptado}")
            else:
                print(linea.strip())
except FileNotFoundError:
    print("[!] Aún no existen registros de transacciones para desencriptar.")
print("===================================================\n")
