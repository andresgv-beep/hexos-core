import sys, zipfile, xml.etree.ElementTree as ET
with zipfile.ZipFile(sys.argv[1]) as document:
    part = document.getinfo('word/document.xml')
    if part.file_size > 16 * 1024 * 1024:
        raise ValueError('Documento demasiado grande al descomprimir')
    root = ET.fromstring(document.read(part))
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    for paragraph in root.iter(ns + 'p'):
        print(''.join(node.text or '' for node in paragraph.iter(ns + 't')))
