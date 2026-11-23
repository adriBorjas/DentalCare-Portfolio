# DentalCare

Aplicación Django para gestionar una clínica dental: usuarios con roles, pacientes, tratamientos, agenda clínica y reservas públicas.

## Instalación local

Requiere Python 3.12 o superior. Las dependencias están en `requirements.txt`.

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

En PowerShell, activa el entorno con `.\\.venv\\Scripts\\Activate.ps1`. Define las variables en la sesión local; `.env.example` sirve como plantilla y no se carga automáticamente:

```powershell
$env:DJANGO_SECRET_KEY = "genera-una-clave-local-segura"
$env:DJANGO_DEBUG = "True"
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost"
```

`DEBUG` está desactivado por defecto. Para desarrollo local se puede activar con `DJANGO_DEBUG=True`.

Aplica migraciones y carga datos ficticios:

```bash
python manage.py migrate
python manage.py poblar_datos
```

El comando genera contraseñas aleatorias al crear los usuarios demo y no las deja escritas en el código ni en este README. Los teléfonos, documentos, direcciones y correos del conjunto demo son ficticios; los correos usan el dominio reservado `example.test`.

Para ejecutar la aplicación solo en local:

```bash
python manage.py runserver
```

## Pruebas

```bash
python manage.py check
python manage.py test
```

## Estructura

- `accounts`: usuarios, roles y perfiles de pacientes/dentistas.
- `appointments`: agenda, disponibilidad y citas.
- `treatments`: catálogo de tratamientos.
- `core`: páginas generales y comando de datos demo.
- `templates`: plantillas HTML.
- `static`: recursos estáticos.

## Configuración segura

No subas archivos `.env`, bases de datos locales ni secretos. `.env.example` es la única variante de entorno permitida en el repositorio. La clave histórica del proyecto debe considerarse comprometida; cualquier entorno real debe usar una clave nueva y gestionar sus credenciales fuera de Git.

### `SECRET_KEY` y base de datos demo

`SECRET_KEY` es una credencial criptográfica de Django: se utiliza para firmar sesiones, cookies y otros tokens. No es un dato de la base de datos ni un valor que deba compartirse en un portfolio. La clave antigua se considera comprometida y cada instalación real debe definir una nueva mediante `DJANGO_SECRET_KEY`.

La base `portfolio_demo.sqlite3` es únicamente una base local de demostración, no se versiona y está excluida por `.gitignore`. Sus registros son ficticios y se pueden regenerar con `migrate` y `poblar_datos`.
