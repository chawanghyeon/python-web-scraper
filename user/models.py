from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.BigAutoField(primary_key=True, unique=True)

    def __unicode__(self):
        return self.first_name

    def __str__(self):
        return self.first_name

    class Meta:
        app_label = "user"