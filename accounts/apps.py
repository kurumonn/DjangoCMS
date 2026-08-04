from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "アカウント"

    def ready(self):
        # システムチェックを登録する。
        # import しないと @register デコレータが実行されない。
        from . import checks  # noqa: F401
