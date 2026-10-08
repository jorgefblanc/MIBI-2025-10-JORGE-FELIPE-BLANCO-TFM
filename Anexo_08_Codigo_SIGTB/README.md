# Anexo 8. Código fuente del SIGTB

Código fuente del piloto del **Sistema Integrado de Gestión de Tecnología Biomédica (SIGTB)**,
desarrollado para el Trabajo Fin de Máster de Jorge Felipe Blanco Medina
(Máster Universitario en Ingeniería Biomédica, Universidad Internacional de Valencia).

Este anexo muestra la aplicación tal como se usó en el piloto. No incluye inventarios
institucionales, bases de datos con datos reales, archivos `.env` ni secretos de despliegue.

## Cómo encajan las piezas

| Carpeta | Rol |
|---------|-----|
| `public/` | Interfaz: `index.html`, estilos y JavaScript del navegador. |
| `server/` | Servidor Flask: autenticación, permisos, inventario e instrumentos. |
| `sql/` | Esquemas SQLite que el servidor aplica al arrancar. |
| `data/` | Se crea al ejecutar la aplicación (bases SQLite, respaldos, logs). No se publica. |

Flujo habitual: el navegador carga `public/index.html`, el usuario inicia sesión y cada
módulo llama a rutas HTTP del servidor (`/api/...`, `/admin/...`). El servidor lee y
escribe en SQLite bajo `data/`.

## Módulos incluidos

- Organización e inventario (empresa → sede → servicio → equipos).
- Forma de adquisición (comodato / leasing / compra; afecta el dimensionamiento).
- Suficiencia, dimensionamiento, frecuencia de mantenimiento preventivo y preinstalación.
- KPIs de ingeniería clínica (instrumento gerencial presente en el piloto).
- Usuarios, roles (RBAC), bandeja de solicitudes y respaldos.

El panel CAPEX aparece en el menú como reservado: no tiene motor de cálculo en esta
versión. El alcance completo y lo que queda fuera se describen en el Anexo 4.

## Arranque (local)

1. Python 3.10 o superior y un entorno virtual.
2. `pip install -r requirements.txt`
3. Variables de entorno: `SIGTB_ADMIN_PASSWORD` es obligatoria en el primer arranque;
   `SECRET_KEY` es obligatoria en producción (`SIGTB_ENV=production`).

```bash
export SIGTB_ADMIN_PASSWORD='CAMBIAR_ANTES_DE_USAR'   # cámbiela
export SECRET_KEY='CAMBIAR_ANTES_DE_USAR'              # cámbiela
```

4. Desde la raíz de este anexo:

```bash
python -m server.app
```

5. Abrir `http://127.0.0.1:3000` (puerto configurable con `PORT`).

Al ejecutarse así, `server/app.py` detiene cualquier proceso que ocupe el puerto y, en
Windows, intenta abrirlo en el firewall de red privada para el acceso por LAN.

En el primer arranque se crean las bases y un administrador
(`admin@sigtb.local`) más perfiles demo (`direccion@`, `coordinador@`,
`ingeniero@`, `asistencial@` en el dominio `sigtb.local`) con la misma
contraseña de `SIGTB_ADMIN_PASSWORD`.

Para correo real de recuperación de contraseña, configure `SMTP_HOST`,
`SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` y `SMTP_FROM` (o un `data/smtp.json`).
Sin SMTP, el sistema deja el enlace en bandeja local.

## Secretos y datos omitidos

Se retiraron o sustituyeron por el marcador `CAMBIAR_ANTES_DE_USAR`:

- Contraseña inicial del administrador (antes en `server/db.py`).
- Clave de sesión de desarrollo (antes en `server/app.py`).
- Rutas locales personales a CSV/Excel de importación.
- Referencias a un nombre de usuario en la detección de copias OneDrive.

No se incluyen `.env`, dumps SQLite, inventarios FOSCAGIB, claves AWS ni
documentación interna con demos de contraseña (`MAPA_MODULOS.md` y similares).
