from django.db import models


class Station(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=10, decimal_places=8)  # source has 8 dp; Decimal keeps cost math exact
    # ponytail: city centroid from Census Gazetteer (a few miles off), geocode addresses offline if precision matters
    lat = models.FloatField()
    lon = models.FloatField()

    def __str__(self):
        return f'{self.name} ({self.city}, {self.state})'
