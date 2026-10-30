from datetime import date

import pytest
from app.leave_policy import days_in_year
from conftest import DEV, HR, ORG_B, headers, login
from test_workforce_investigations import employee


@pytest.mark.parametrize("counting,expected", [("calendar", 2), ("weekdays", 0)])
def test_holidays_are_excluded_once_and_weekends_follow_calendar_mode(counting, expected):
    # Friday through Sunday; the Friday is a holiday.
    assert (
        days_in_year(date(2026, 12, 25), date(2026, 12, 27), 2026, counting, ["2026-12-25"])
        == expected
    )


def test_holiday_balance_reservation_and_calendar_mutation_guard(client, db):
    record = employee(db)
    endpoint = f"/api/v1/hr/employees/{record.id}/leave-allowance/2026"
    login(HR)
    policy = {"allowance_days": 1, "holidays": ["2026-12-25"]}
    response = client.put(endpoint, headers=headers(), json=policy)
    assert response.status_code == 200, response.text
    assert response.json()["holidays"] == ["2026-12-25"]
    login(DEV)
    response = client.post(
        "/api/v1/hr/leave",
        headers=headers(),
        json={
            "employee_id": record.id,
            "starts_on": "2026-12-24",
            "ends_on": "2026-12-27",
            "reason": "Fixture",
        },
    )
    assert response.status_code == 201, response.text
    leave_id = response.json()["id"]
    balance = client.get(endpoint, headers=headers()).json()
    assert balance["reserved_days"] == 1 and balance["remaining_days"] == 0
    login(HR)
    assert (
        client.put(endpoint, headers=headers(), json=policy | {"holidays": []}).status_code == 409
    )
    assert (
        client.put(endpoint, headers=headers(), json=policy | {"allowance_days": 2}).status_code
        == 200
    )
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    assert client.post(f"/api/v1/hr/leave/{leave_id}/cancel", headers=headers()).status_code == 200
    assert (
        client.put(endpoint, headers=headers(), json=policy | {"holidays": []}).status_code == 200
    )


@pytest.mark.parametrize("holidays", [["2027-01-01"], ["2026-12-25", "2026-12-25"], ["not-a-date"]])
def test_invalid_or_out_of_year_holidays_are_rejected(client, db, holidays):
    record = employee(db)
    login(HR)
    assert (
        client.put(
            f"/api/v1/hr/employees/{record.id}/leave-allowance/2026",
            headers=headers(),
            json={
                "allowance_days": 20,
                "holidays": holidays,
            },
        ).status_code
        == 422
    )


def test_zero_charge_reservation_still_prevents_retroactive_calendar_changes(client, db):
    record = employee(db)
    endpoint = f"/api/v1/hr/employees/{record.id}/leave-allowance/2026"
    policy = {"allowance_days": 0, "holidays": ["2026-12-25"]}
    login(HR)
    assert client.put(endpoint, headers=headers(), json=policy).status_code == 200
    login(DEV)
    response = client.post(
        "/api/v1/hr/leave",
        headers=headers(),
        json={
            "employee_id": record.id,
            "starts_on": "2026-12-25",
            "ends_on": "2026-12-25",
            "reason": "Fixture",
        },
    )
    assert response.status_code == 201, response.text
    login(HR)
    assert (
        client.put(endpoint, headers=headers(), json=policy | {"holidays": []}).status_code == 409
    )


def test_cross_year_calendars_charge_each_year_independently(client, db):
    record = employee(db)
    login(HR)
    for year, holidays in [(2026, ["2026-12-31"]), (2027, ["2027-01-01"])]:
        response = client.put(
            f"/api/v1/hr/employees/{record.id}/leave-allowance/{year}",
            headers=headers(),
            json={
                "allowance_days": 0,
                "counting": "calendar",
                "holidays": holidays,
            },
        )
        assert response.status_code == 200, response.text
    login(DEV)
    response = client.post(
        "/api/v1/hr/leave",
        headers=headers(),
        json={
            "employee_id": record.id,
            "starts_on": "2026-12-31",
            "ends_on": "2027-01-01",
            "reason": "Fixture",
        },
    )
    assert response.status_code == 201, response.text
    for year in [2026, 2027]:
        assert (
            client.get(
                f"/api/v1/hr/employees/{record.id}/leave-allowance/{year}", headers=headers()
            ).json()["reserved_days"]
            == 0
        )
