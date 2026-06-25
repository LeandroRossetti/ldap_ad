# ldap_ad

Sistema web de gestión de stock con autenticación contra **Active Directory**. Los usuarios inician sesión con sus credenciales de AD y acceden a funcionalidades según su rol (Admin, Operador o Consulta), mapeado desde grupos del dominio. Incluye control horario configurable por usuario.

## Requisitos

- Python 3.10+
- Servidor Active Directory accesible en la red

## Instalación

```bash
# Crear entorno virtual
python -m venv venv

# Activar (Windows)
.\venv\Scripts\activate

# Activar (Linux/Mac)
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## Configuración

Copiar `.env.example` a `.env` y completar los valores:

```ini
SECRET_KEY=clave_secreta
AD_SERVER=ip_del_servidor_ad
AD_PORT=389
AD_DOMAIN=DOMINIO
AD_BASE_DN=dc=dominio,dc=local
HORA_INICIO=8
HORA_FIN=18
AD_GRUPO_ADMIN=Domain Admins,Administrators
AD_GRUPO_OPERADOR=
AD_GRUPO_CONSULTA=
DATABASE_PATH=stock.db
```

Los roles se asignan según pertenencia a grupos de AD indicados en `AD_GRUPO_ADMIN`, `AD_GRUPO_OPERADOR` y `AD_GRUPO_CONSULTA`.

El horario permitido se configura globalmente con `HORA_INICIO`/`HORA_FIN`, y puede personalizarse por usuario agregando en AD el atributo `info` con el formato `inicio-fin` (ej. `7-15`).

## Uso

```bash
python app.py
```

La aplicación arranca en `http://localhost:5000`.

## Funcionalidades

| Rol | Acceso |
|---|---|
| **Admin** | ABM completo de productos, movimientos, reportes y exportación CSV |
| **Operador** | Solo carga de movimientos (entrada/salida) |
| **Consulta** | Solo visualización de productos, movimientos y reportes |

- Productos con control de stock mínimo (se marcan en rojo si están por debajo)
- Registro de movimientos con tipo (entrada/salida), cantidad y observaciones
- Exportación de stock y movimientos a CSV
- Persistencia en SQLite

## Tecnologías

- **Flask 3.1** — Framework web
- **ldap3** — Autenticación contra Active Directory
- **SQLite** — Base de datos embebida
- **Bootstrap 5.3** — Interfaz responsive
