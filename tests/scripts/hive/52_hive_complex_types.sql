SELECT
    e.event_id,
    e.properties['utm_source']                      AS utm_source,
    e.items[0].sku                                  AS first_sku,
    size(e.items)                                   AS item_count,
    get_json_object(e.payload, '$.customer.address.city') AS city,
    json_tuple_alias.plan,
    named_struct('visitor', e.visitor_id, 'day', e.event_date) AS visitor_day,
    map('source', e.properties['utm_source'], 'medium', 'web') AS tags,
    array(e.visitor_id, 0, -1)                      AS ids,
    item.sku,
    item.qty * item.price                           AS line_total,
    pos                                             AS item_position,
    collect_set(item.sku) OVER (PARTITION BY e.visitor_id) AS all_skus,
    regexp_extract(e.page_url, '^https?://([^/]+)/', 1) AS host,
    concat_ws('|', e.region, cast(e.visitor_id AS STRING)) AS visitor_key
FROM lake_raw.click_events e
LATERAL VIEW OUTER posexplode(e.items) exploded AS pos, item
LATERAL VIEW json_tuple(e.payload, 'plan', 'tier') json_tuple_alias AS plan, tier
WHERE e.event_date BETWEEN '2024-06-01' AND '2024-06-30'
  AND e.properties['consent'] = 'granted'
  AND array_contains(split(e.segments, ','), 'vip')
  AND item.price > 99.5;
