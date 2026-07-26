from django.apps import AppConfig


class MediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.media"
    # Label avoids any clash with Django's own "media" naming, mirroring the
    # secret store's "vault" label.
    label = "assets"
    verbose_name = "Media Assets"
