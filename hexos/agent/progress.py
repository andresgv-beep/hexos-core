"""Preámbulo visible del modelo; respaldo genérico si no lo genera."""


def announcement(preamble=None):
    if isinstance(preamble,str) and preamble.strip() and len(preamble)<=1000:
        return preamble.strip()
    return 'Me pongo con ello y te cuento el resultado.'
