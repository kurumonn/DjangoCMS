from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "共通"

    def ready(self):
        # システムチェックを登録する。
        # import しないと @register デコレータが実行されない。
        from . import checks  # noqa: F401
