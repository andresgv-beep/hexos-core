# SQLite: cambiar el esquema cuando ya hay datos
aplica: sqlite3, sqlite, .db, .sqlite

`CREATE TABLE IF NOT EXISTS` no cambia una tabla que ya existe. Si añades una columna solo ahí, el programa funciona en una base nueva y falla en la de la persona con «no such column».

- Cada cambio de esquema es una migración que se aplica a la base que ya hay, al arrancar.
- Lleva la cuenta con `PRAGMA user_version`: lee la versión, aplica lo que falte en orden y súbela.
- Para una columna: `ALTER TABLE tabla ADD COLUMN nombre TIPO`. Comprueba antes con `PRAGMA table_info(tabla)` si ya está, para que repetirlo no falle.
- No escribas un script aparte para arreglar la base a mano: la migración va dentro del programa.
- La ruta de la base, relativa al fichero del programa y no al directorio desde el que se lanza; si no, cada sitio crea su propia base vacía.

```python
RUTA = Path(__file__).with_name('inventario.db')
MIGRACIONES = ['CREATE TABLE componentes (id INTEGER PRIMARY KEY, modelo TEXT)',
               'ALTER TABLE componentes ADD COLUMN imagen TEXT']

def abrir():
    db = sqlite3.connect(RUTA)
    version = db.execute('PRAGMA user_version').fetchone()[0]
    for numero, orden in enumerate(MIGRACIONES[version:], version + 1):
        db.execute(orden)
        db.execute('PRAGMA user_version = %d' % numero)
    db.commit()
    return db
```

Usa siempre parámetros (`?`) en las consultas, nunca texto pegado.
