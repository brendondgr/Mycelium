from django.http import JsonResponse
from django.urls import path


def hello(request):
    return JsonResponse({"hello": "fixture"})


urlpatterns = [path("fixture-leaf/", hello, name="fixture-leaf")]
