def greeting() -> str:
    from django.conf import settings

    return settings.FIXTURE_OK_LEAF_GREETING
