from django.apps import AppConfig


class SecretsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.secrets"
    label = "vault"  # avoid any clash with the stdlib `secrets` app label
    verbose_name = "Secret Store"
