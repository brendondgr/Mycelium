from django.contrib.auth.models import User


def user_to_dict(user: User) -> dict[str, object]:
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }
