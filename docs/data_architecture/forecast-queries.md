# Forecast Queries

> **Status: IMPLEMENTED** | Last verified: 2026-03-06

Example SQL queries against the [Forecast Schema](forecast-schema.md). These target the forecast analytical layer stored under `processed/forecast/analytics/` and work with DuckDB, Athena, or any SQL engine reading the Parquet files.

---

## 1. Basic Time-Series Query

Get wave conditions for a spot over a week:

```sql
SELECT
    forecast_ts,
    surf_min,
    surf_max,
    surf_human_relation,
    power
FROM fact_wave
WHERE spot_id = '584204204e65fad6a77090d2'
  AND forecast_ts BETWEEN '2026-01-10' AND '2026-01-17'
ORDER BY forecast_ts;
```

## 2. Cross-Forecast Join

Combine wave + wind + rating for the same timestamps:

```sql
SELECT
    w.forecast_ts,
    w.surf_min,
    w.surf_max,
    wind.speed AS wind_speed,
    wind.direction_type,
    r.rating_key,
    r.rating_value
FROM fact_wave w
JOIN fact_wind wind
    ON w.spot_id = wind.spot_id
    AND w.forecast_ts = wind.forecast_ts
    AND w.scrape_ts = wind.scrape_ts
JOIN fact_rating r
    ON w.spot_id = r.spot_id
    AND w.forecast_ts = r.forecast_ts
    AND w.scrape_ts = r.scrape_ts
WHERE w.spot_id = '584204204e65fad6a77090d2'
  AND w.forecast_ts >= '2026-01-17';
```

## 3. Swell Analysis

Find spots with long-period swells (the main benefit of the separate swells table):

```sql
SELECT
    sw.spot_id,
    AVG(sw.period) AS avg_period,
    MAX(sw.height) AS max_height,
    SUM(sw.impact) AS total_impact
FROM fact_swells sw
WHERE sw.forecast_ts >= CURRENT_DATE
  AND sw.period >= 12
  AND sw.impact > 0.2
GROUP BY sw.spot_id
HAVING AVG(sw.period) >= 14
ORDER BY avg_period DESC;
```

## 4. Daylight Filtering

Get wave conditions during daylight hours only:

```sql
SELECT
    w.forecast_ts,
    w.surf_min,
    w.surf_max
FROM fact_wave w
JOIN dim_sunlight sun
    ON w.spot_id = sun.spot_id
    AND DATE(w.forecast_ts) = sun.date
WHERE w.spot_id = '584204204e65fad6a77090d2'
  AND w.forecast_ts >= sun.sunrise
  AND w.forecast_ts <= sun.sunset
ORDER BY w.forecast_ts;
```

## 5. Rating Distribution Over Time

```sql
SELECT
    DATE_TRUNC('day', forecast_ts) AS date,
    rating_key,
    COUNT(*) AS hours
FROM fact_rating
WHERE spot_id = '584204204e65fad6a77090d2'
  AND forecast_ts >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
```

## 6. Best Conditions Finder

Find hours with good waves, offshore wind, and favorable rating:

```sql
SELECT
    w.forecast_ts,
    w.surf_min,
    w.surf_max,
    wind.speed,
    wind.direction_type,
    r.rating_key
FROM fact_wave w
JOIN fact_wind wind
    ON w.spot_id = wind.spot_id
    AND w.forecast_ts = wind.forecast_ts
    AND w.scrape_ts = wind.scrape_ts
JOIN fact_rating r
    ON w.spot_id = r.spot_id
    AND w.forecast_ts = r.forecast_ts
    AND w.scrape_ts = r.scrape_ts
WHERE w.spot_id = '584204204e65fad6a77090d2'
  AND w.surf_min >= 3
  AND wind.direction_type = 'Offshore'
  AND wind.speed < 15
  AND r.rating_value >= 4
ORDER BY w.forecast_ts;
```

---

## Reconstructing Original Data

The Parquet schema is a lossy transformation — the `associated` metadata objects from the original JSON are not stored in dedicated tables. Individual forecast values can be reconstructed but the full round-trip back to original JSON format is not supported.

### Rebuild Rating JSON Array

```sql
SELECT JSON_GROUP_ARRAY(
    JSON_OBJECT(
        'timestamp', CAST(EXTRACT(EPOCH FROM forecast_ts) AS INTEGER),
        'utcOffset', utc_offset,
        'rating', JSON_OBJECT(
            'key', rating_key,
            'value', rating_value
        )
    ) ORDER BY forecast_ts
) AS rating_array
FROM fact_rating
WHERE spot_id = '584204204e65fad6a77090d2'
  AND scrape_ts = '2026-01-17T14:43:39.398066';
```

### Rebuild Wave + Swells JSON

```sql
WITH swells_agg AS (
    SELECT
        spot_id,
        forecast_ts,
        scrape_ts,
        JSON_GROUP_ARRAY(
            JSON_OBJECT(
                'height', height,
                'period', period,
                'impact', impact,
                'power', power,
                'direction', direction,
                'directionMin', direction_min,
                'optimalScore', optimal_score
            ) ORDER BY swell_index
        ) AS swells_json
    FROM fact_swells
    GROUP BY spot_id, forecast_ts, scrape_ts
)
SELECT
    w.forecast_ts,
    JSON_OBJECT(
        'timestamp', CAST(EXTRACT(EPOCH FROM w.forecast_ts) AS INTEGER),
        'probability', w.probability,
        'utcOffset', w.utc_offset,
        'surf', JSON_OBJECT(
            'min', w.surf_min,
            'max', w.surf_max,
            'plus', w.surf_plus,
            'humanRelation', w.surf_human_relation,
            'raw', JSON_OBJECT(
                'min', w.surf_raw_min,
                'max', w.surf_raw_max
            ),
            'optimalScore', w.surf_optimal_score
        ),
        'power', w.power,
        'swells', sw.swells_json
    ) AS wave_entry
FROM fact_wave w
LEFT JOIN swells_agg sw
    ON w.spot_id = sw.spot_id
    AND w.forecast_ts = sw.forecast_ts
    AND w.scrape_ts = sw.scrape_ts
WHERE w.spot_id = '584204204e65fad6a77090d2'
  AND w.scrape_ts = '2026-01-17T14:43:39.398066'
ORDER BY w.forecast_ts;
```
