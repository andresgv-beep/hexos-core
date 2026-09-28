"""Imágenes adjuntas: orientación EXIF y reducción."""
import base64
import io
import unittest

from PIL import Image

from hexos.agent.chat_backend.images import decode_image


def jpeg(width, height, orientation=None):
    imagen = Image.new('RGB', (width, height), (200, 30, 30))
    imagen.paste((30, 30, 200), (0, 0, width // 4, height))   # franja a la izquierda
    buf = io.BytesIO()
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        imagen.save(buf, 'JPEG', exif=exif)
    else:
        imagen.save(buf, 'JPEG')
    return base64.b64encode(buf.getvalue()).decode()


class ImagesTest(unittest.TestCase):
    def test_vertical_photo_stored_landscape_arrives_upright(self):
        # Como un iPhone: píxeles en horizontal y la etiqueta «gira 90°» (6).
        pixels, width, height = decode_image(jpeg(2000, 1500, orientation=6))
        self.assertEqual((width, height), (1152, 1536))

    def test_without_exif_nothing_rotates(self):
        pixels, width, height = decode_image(jpeg(2000, 1500))
        self.assertEqual((width, height), (1536, 1152))
        self.assertEqual(len(pixels), width * height * 3)


if __name__ == '__main__':
    unittest.main()
