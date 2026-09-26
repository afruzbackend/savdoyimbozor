"""Statik fayllar saqlagichi (prod): WhiteNoise siqilgan manifest + yo'q havolalarga chidamli."""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticStorage(CompressedManifestStaticFilesStorage):
    """Fayl nomiga xesh (abadiy kesh) + gzip/brotli. Vendor CSS ichidagi ishlatilmaydigan, lekin
    loyihada yo'q rasmga havola (leaflet.css → images/layers.png) collectstatic'ni to'xtatmasin —
    bunday havola o'zgartirilmay qoladi."""

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            return name
