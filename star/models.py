from django.db import models

from repository.models import Repository
from user.models import User


class Star(models.Model):
    id = models.BigAutoField(primary_key=True, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="star"
    )

    def __unicode__(self):
        return self.user.first_name + " " + self.repository.name

    def __str__(self):
        return self.user.first_name + " " + self.repository.name
