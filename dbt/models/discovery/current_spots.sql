select *
from {{ source('public', 'discovery_spot_versions') }}
where is_current = true
  and event_type <> 'removed'
