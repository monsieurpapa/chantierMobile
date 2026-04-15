from storages.backends.s3boto3 import S3Boto3Storage


class MediaStorage(S3Boto3Storage):
    """
    Cloudflare R2 (S3-compatible) storage for user-uploaded media files.

    Cabinet logos and expense receipt images are stored here in production.
    Files are served from the R2 public bucket URL (or a custom domain if configured).

    Usage: set DEFAULT_FILE_STORAGE = 'chantiermobile.storage_backends.MediaStorage'
    in settings.py (already done for non-DEBUG environments).
    """

    location = "media"
    file_overwrite = False
