from django.db import models

class Prediction_values(models.Model):
    index = models.DateTimeField(unique=True,blank=False,null=False)
    predicted = models.IntegerField(blank=False,null=False)
    predicted_prob = models.FloatField(blank=False,null=False)

    def __str__(self):
        return f'{self.index}'