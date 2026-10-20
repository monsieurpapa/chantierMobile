"""Custom storage backends for production (see the STORAGES setting):
MediaStorage for uploads on Cloudflare R2, StaticStorage for static files."""
from storages.backends.s3boto3 import S3Boto3Storage
from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticStorage(CompressedManifestStaticFilesStorage):
    """Hashed, gzip/brotli-compressed static files, cached for a year by
    WhiteNoise. `manifest_strict = False`: a {% static %} path missing from
    the manifest falls back to its plain URL instead of raising (which
    would turn one missing asset into a 500 on every page)."""

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        """Keep a reference to a missing file unchanged instead of failing
        collectstatic. Several vendored theme stylesheets point at images
        that were never shipped (e.g. leaflet.css -> images/layers.png);
        without this, one such reference aborts collectstatic, and the
        container (which runs it on boot) would fail to start."""
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            if content is not None:
                raise
            return name


class MediaStorage(S3Boto3Storage):
    """
    Cloudflare R2 (S3-compatible) storage for user-uploaded media files.

    Cabinet logos and expense receipt images are stored here in production.
    Files are served from the R2 public bucket URL (or a custom domain if configured).

    Selected via STORAGES['default'] in settings.py for non-DEBUG environments.
    """

    location = "media"
    file_overwrite = False
