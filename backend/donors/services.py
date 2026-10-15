import math

from django.db import connection
from django.db.models.expressions import RawSQL

from .models import DonorProfile


def nearby_available_donors(hospital, blood_group, radius_km=5):
    """Return nearby donors using PostGIS or a portable local-development fallback."""
    if hospital.latitude is None or hospital.longitude is None:
        return DonorProfile.objects.none()

    candidates = DonorProfile.objects.filter(
        blood_group=blood_group,
        is_available=True,
        latitude__isnull=False,
        longitude__isnull=False,
    ).select_related("user")
    if connection.vendor != "postgresql":
        hospital_latitude = math.radians(float(hospital.latitude))
        hospital_longitude = math.radians(float(hospital.longitude))
        radius_m = radius_km * 1000
        nearby = []
        for donor in candidates:
            donor_latitude = math.radians(float(donor.latitude))
            donor_longitude = math.radians(float(donor.longitude))
            latitude_delta = donor_latitude - hospital_latitude
            longitude_delta = donor_longitude - hospital_longitude
            haversine = (
                math.sin(latitude_delta / 2) ** 2
                + math.cos(hospital_latitude)
                * math.cos(donor_latitude)
                * math.sin(longitude_delta / 2) ** 2
            )
            distance_m = 6_371_000 * 2 * math.asin(math.sqrt(min(1, haversine)))
            if distance_m <= radius_m:
                nearby.append((distance_m, donor))
        return [donor for _, donor in sorted(nearby, key=lambda item: item[0])]

    donor_point = "ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography"
    hospital_point = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography"
    distance_expression = f"ST_Distance({donor_point}, {hospital_point})"

    return (
        candidates
        .annotate(
            distance_m=RawSQL(
                distance_expression,
                [hospital.longitude, hospital.latitude],
            )
        )
        .filter(distance_m__lte=radius_km * 1000)
        .select_related("user")
        .order_by("distance_m")
    )


def donors_for_shortage(shortage_request):
    return nearby_available_donors(
        shortage_request.hospital,
        shortage_request.blood_group,
        shortage_request.radius_km,
    )