from ldap3 import Server, Connection, SUBTREE

server = Server('pp3', port=389)

conn = Connection(
    server,
    user='IFTS\\Administrator',
    password='IFTS.2026',
    auto_bind=True
)

print("Conectado exitosamente al AD.\n")

# --- NUEVAS LÍNEAS PARA LISTAR USUARIOS ---

# 1. Definir la base de búsqueda (Ajustá esto si tu dominio no es IFTS.local)
base_dn = 'dc=IFTS,dc=local'

# 2. Filtro estándar de Active Directory para buscar usuarios
filtro = '(&(objectCategory=person)(objectClass=user))'

# 3. Ejecutar la búsqueda
conn.search(
    search_base=base_dn,
    search_filter=filtro,
    search_scope=SUBTREE, # Busca en la raíz y en todas las carpetas/OUs hacia abajo
    attributes=['sAMAccountName', 'cn', 'memberOf'] # Queremos el nombre de login y el nombre completo
)

# 4. Recorrer e imprimir los resultados
print(f"Se encontraron {len(conn.entries)} usuarios:")
print("-" * 30)

for entrada in conn.entries:
    # sAMAccountName es el usuario de login (ej: jramos)
    # cn (Common Name) suele ser el nombre y apellido
    usuario = entrada.sAMAccountName
    nombre_completo = entrada.cn
    miembro = entrada.memberOf
    cnt= str(miembro).split(',')[0].replace('CN=', '')
    print(f"Login: {usuario} | Nombre: {nombre_completo}  | Miembro: {cnt}")
