"""Decodificación y reducción de imágenes, fuera del ciclo del agente."""
from __future__ import annotations

import base64
import binascii
import io
from .settings import MAX_IMAGE_SIDE


def decode_image(encoded):
    """base64 de PNG/JPEG -> (píxeles RGB8, ancho, alto). None si no hay imagen."""
    if encoded is None:
        return None
    if not isinstance(encoded, str) or not encoded:
        raise ValueError('image debe ser una cadena base64 de una imagen')
    try:
        crudo = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('image no es base64 válido') from exc
    if len(crudo) > 16 * 1024 * 1024:
        raise ValueError('imagen mayor de 16 MiB')
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ValueError('falta Pillow en el servidor; no se pueden leer imágenes') from exc
    try:
        imagen = Image.open(io.BytesIO(crudo))
        imagen.load()
    except Exception as exc:
        raise ValueError('no se pudo leer la imagen: ' + str(exc)) from exc
    # Los móviles guardan muchas fotos en horizontal con una etiqueta EXIF de giro.
    # Sin aplicarla, el modelo recibía tumbada una foto vertical (1536x1152) y no
    # leía el texto: una placa ESP32 se tomó por una Raspberry Pi (28/09).
    imagen = ImageOps.exif_transpose(imagen)
    imagen = imagen.convert('RGB')
    # El preprocesado de Gemma reescala a su propio tamaño; por encima de esto
    # solo se transportarían píxeles que se van a tirar.
    if max(imagen.size) > MAX_IMAGE_SIDE:
        escala = MAX_IMAGE_SIDE / max(imagen.size)
        imagen = imagen.resize((max(1, round(imagen.width * escala)),
                                max(1, round(imagen.height * escala))))
    return imagen.tobytes(), imagen.width, imagen.height
