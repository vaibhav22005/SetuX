from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from django.utils import timezone as dj_timezone

from .models import BloodInventory

BLOOD_GROUPS = [
    "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-",
]


def generate_synthetic_inventory_history(hospital, blood_group, days=365, baseline_units=35):
    """Generate a year of reproducible daily inventory with seasonal pressure."""
    if days < 1:
        raise ValueError("days must be at least 1")
    if baseline_units < 0:
        raise ValueError("baseline_units cannot be negative")

    today = dj_timezone.now().date()
    records = []
    for offset in range(days):
        stock_day = today - timedelta(days=(days - offset - 1))
        annual_cycle = 5 * math.sin((stock_day.timetuple().tm_yday / 365.0) * math.tau)
        monthly_cycle = 4 * math.sin((offset / 30.0) * math.tau)
        seasonal_pressure = 10 if stock_day.month in {6, 7, 8, 9} else 0
        replenishment = 8 if offset % 23 == 0 else 0
        units = int(round(baseline_units + annual_cycle + monthly_cycle + replenishment - seasonal_pressure))
        units = max(0, min(100, units))
        threshold = max(5, round(baseline_units * 0.35))
        records.append(
            BloodInventory(
                hospital=hospital,
                blood_group=blood_group,
                units_available=units,
                safe_threshold=threshold,
                recorded_at=datetime.combine(stock_day, datetime.min.time(), tzinfo=timezone.utc),
            )
        )
    return records


def save_synthetic_inventory_history(hospital, blood_group=None, days=365, baseline_units=35):
    """Persist synthetic history for one or more blood groups if it has not already been seeded."""
    groups = [blood_group] if blood_group else BLOOD_GROUPS
    created = 0
    for group in groups:
        records = generate_synthetic_inventory_history(
            hospital,
            group,
            days=days,
            baseline_units=baseline_units,
        )
        if not records:
            continue
        existing_dates = set(
            BloodInventory.objects.filter(
                hospital=hospital,
                blood_group=group,
                recorded_at__date__range=(
                    records[0].recorded_at.date(),
                    records[-1].recorded_at.date(),
                ),
            ).values_list("recorded_at__date", flat=True)
        )
        missing_records = [
            record for record in records
            if record.recorded_at.date() not in existing_dates
        ]
        BloodInventory.objects.bulk_create(missing_records)
        created += len(missing_records)
    return created


def forecast_inventory_risk_for_group(hospital, blood_group, days_ahead=7):
    """Fit a linear regression to recent stock history and return its risk forecast."""
    if days_ahead < 1:
        raise ValueError("days_ahead must be at least 1")

    history = list(
        BloodInventory.objects.filter(hospital=hospital, blood_group=blood_group)
        .order_by("-recorded_at")[:90]
    )
    history.reverse()
    if not history:
        return {
            "blood_group": blood_group,
            "current_units": 0,
            "safe_threshold": 0,
            "risk_level": "missing_data",
            "forecast": [],
        }

    current_units = history[-1].units_available
    safe_threshold = history[-1].safe_threshold or 5
    values = [item.units_available for item in history]
    first_day = history[0].recorded_at.date()
    time_steps = [(item.recorded_at.date() - first_day).days for item in history]
    mean_time = sum(time_steps) / len(time_steps)
    mean_units = sum(values) / len(values)
    variance = sum((step - mean_time) ** 2 for step in time_steps)
    slope = (
        sum((step - mean_time) * (units - mean_units) for step, units in zip(time_steps, values))
        / variance
        if variance
        else 0
    )
    intercept = mean_units - slope * mean_time

    forecast = []
    last_recorded_date = history[-1].recorded_at.date()
    for offset in range(1, days_ahead + 1):
        predicted = max(0, round(intercept + slope * (time_steps[-1] + offset)))
        forecast.append(
            {
                "day_offset": offset,
                "date": last_recorded_date + timedelta(days=offset),
                "predicted_units": predicted,
            }
        )

    high_risk = any(item["predicted_units"] <= safe_threshold * 0.75 for item in forecast)
    watch_risk = any(item["predicted_units"] <= safe_threshold for item in forecast)
    if current_units <= safe_threshold or high_risk:
        risk_level = "high"
    elif watch_risk:
        risk_level = "watch"
    else:
        risk_level = "healthy"

    return {
        "blood_group": blood_group,
        "current_units": current_units,
        "safe_threshold": safe_threshold,
        "risk_level": risk_level,
        "forecast": forecast,
    }


def _risk_priority(risk_level):
    return {"high": 0, "watch": 1, "healthy": 2, "missing_data": 3}.get(risk_level, 4)


def summarize_inventory_risk_for_hospital(hospital, days_ahead=7):
    """Summarize forecast risk across all blood groups at a hospital."""
    summaries = []
    for blood_group in BLOOD_GROUPS:
        risk = forecast_inventory_risk_for_group(hospital, blood_group, days_ahead=days_ahead)
        if risk["forecast"] or risk["risk_level"] == "missing_data":
            summaries.append(risk)
    return sorted(summaries, key=lambda item: (_risk_priority(item["risk_level"]), item["blood_group"]))


def summarize_inventory_risk_across_hospitals(hospitals, days_ahead=7):
    """Aggregate forecast risk items across hospitals for the operations dashboard."""
    items = []
    for hospital in hospitals:
        for blood_group in BLOOD_GROUPS:
            risk = forecast_inventory_risk_for_group(hospital, blood_group, days_ahead=days_ahead)
            if risk["risk_level"] in {"high", "watch"}:
                items.append({
                    "hospital_id": hospital.pk,
                    "hospital_name": hospital.name,
                    "blood_group": blood_group,
                    "risk_level": risk["risk_level"],
                    "current_units": risk["current_units"],
                    "safe_threshold": risk["safe_threshold"],
                    "next_prediction": risk["forecast"][0] if risk["forecast"] else None,
                })
    return sorted(
        items,
        key=lambda item: (0 if item["risk_level"] == "high" else 1 if item["risk_level"] == "watch" else 2, item["hospital_name"], item["blood_group"]),
    )
