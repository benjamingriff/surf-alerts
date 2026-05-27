import json
from pathlib import Path

from forecast_transform import transform_forecast_envelope


SAMPLE_PATH = Path(__file__).parent / "fixtures/forecast_sample.json"


def sample_envelope():
    return {
        "schema_version": 1,
        "source_type": "surfline_forecast",
        "forecast_run_id": "forecast#offset=1#scrape_date=2026-05-26#time=04-00",
        "spot_id": "5842041f4e65fad6a7708bca",
        "spot_version_id": "spot-version-1",
        "spot_name": "Rest Bay",
        "scheduled_utc_time": "2026-05-26T03:00:00+00:00",
        "scraped_at": "2026-05-26T03:04:00+00:00",
        "utc_offset": 1,
        "timezone": "Europe/London",
        "raw_payload": json.loads(SAMPLE_PATH.read_text()),
    }


def test_transforms_sample_forecast_into_all_five_v1_fact_row_sets():
    rows = transform_forecast_envelope(sample_envelope(), source_raw_key="raw/key.json.gz")

    assert len(rows.ratings) == 1
    assert len(rows.waves) == 1
    assert len(rows.swells) == 6
    assert len(rows.winds) == 1
    assert len(rows.tides) == 3


def test_rating_rows_include_forecast_time_rating_source_offset_run_init_and_lineage():
    row = transform_forecast_envelope(sample_envelope(), source_raw_key="raw/key.json.gz").ratings[
        0
    ]

    assert row["forecast_ts"] == "2026-05-25T23:00:00+00:00"
    assert row["rating_key"] == "POOR_TO_FAIR"
    assert row["rating_value"] == 2.3333333333333335
    assert row["source_utc_offset"] == 1
    assert row["run_init_ts"] == "2026-05-26T00:00:00+00:00"
    assert row["forecast_run_id"].startswith("forecast#offset=1")
    assert row["spot_id"] == "5842041f4e65fad6a7708bca"
    assert row["spot_version_id"] == "spot-version-1"
    assert row["source_raw_key"] == "raw/key.json.gz"
    assert row["schema_version"] == 1


def test_wave_rows_include_surf_power_probability_metadata_and_lineage():
    row = transform_forecast_envelope(sample_envelope(), source_raw_key="raw/key.json.gz").waves[0]

    assert row["forecast_ts"] == "2026-05-25T23:00:00+00:00"
    assert row["surf_min"] == 1
    assert row["surf_max"] == 2
    assert row["surf_plus"] is False
    assert row["surf_human_relation"] == "Knee to thigh"
    assert row["surf_raw_min"] == 0.78084
    assert row["power"] == 15.23004
    assert row["probability"] == 100
    assert row["location_lon"] == -3.728
    assert row["forecast_location_lat"] == 51.473
    assert row["offshore_location_lon"] == -4.6
    assert row["source_raw_key"] == "raw/key.json.gz"


def test_swell_rows_preserve_every_slot_including_zero_height_with_swell_index():
    swells = transform_forecast_envelope(sample_envelope(), source_raw_key="raw/key.json.gz").swells
    first_timestamp = [row for row in swells if row["forecast_ts"] == "2026-05-25T23:00:00+00:00"]

    assert [row["swell_index"] for row in first_timestamp] == [0, 1, 2, 3, 4, 5]
    assert first_timestamp[0]["height"] == 1.28888
    assert first_timestamp[0]["direction_min"] == 247.995625
    assert first_timestamp[2]["height"] == 0
    assert first_timestamp[5]["power"] == 0


def test_wind_rows_include_conditions_metadata_and_lineage():
    row = transform_forecast_envelope(sample_envelope(), source_raw_key="raw/key.json.gz").winds[0]

    assert row["speed"] == 8.43187
    assert row["gust"] == 8.43187
    assert row["direction"] == 69.93409
    assert row["direction_type"] == "Offshore"
    assert row["optimal_score"] == 2
    assert row["source_utc_offset"] == 1
    assert row["location_lat"] == 51.488
    assert row["run_init_ts"] == "2026-05-26T00:00:00+00:00"


def test_tide_rows_preserve_all_entries_in_source_order_with_station_metadata():
    tides = transform_forecast_envelope(sample_envelope(), source_raw_key="raw/key.json.gz").tides

    assert tides[0]["tide_index"] == 0
    assert tides[1]["tide_index"] == 1
    assert tides[-1]["tide_index"] == 2
    assert tides[0]["tide_type"] == "NORMAL"
    assert tides[0]["height"] == 17.24
    assert tides[0]["source_utc_offset"] == 1
    assert tides[0]["tide_location_name"] == "Port Talbot"
    assert tides[0]["tide_location_max"] == 36.32


def test_weather_and_sunlight_inputs_are_ignored():
    envelope = sample_envelope()
    envelope["raw_payload"] = {"weather": {"data": {"weather": [{}]}}, "sunlight": {"data": {}}}

    rows = transform_forecast_envelope(envelope, source_raw_key="raw/key.json.gz")

    assert rows.ratings == []
    assert rows.waves == []
    assert rows.swells == []
    assert rows.winds == []
    assert rows.tides == []
