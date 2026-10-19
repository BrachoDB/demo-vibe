# En orden

Aplicación web de tareas en español, hecha con Flask y SQLite. Cada cuenta tiene
su propio espacio para crear, editar, completar y eliminar tareas.

## Requisitos

- Python 3.10 o posterior
- pip

## Puesta en marcha

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SECRET_KEY = "reemplaza-por-una-clave-larga-y-aleatoria"
python app.py
```

Abre <http://127.0.0.1:5000> en el navegador. La base de datos SQLite se crea
automáticamente en `instance/tasks.sqlite`. Para cambiar su ubicación, define
la variable de entorno `DATABASE`.

## Pruebas

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Las contraseñas se almacenan con hash, las sesiones usan cookies HTTP-only y
SameSite, los formularios POST validan un token CSRF y todas las operaciones de
tareas comprueban la propiedad del usuario en la consulta a la base de datos. La
clave de sesión local se genera al iniciar la aplicación; antes de desplegar,
configura `SECRET_KEY` con un valor aleatorio, persistente y único.
