/* Aggregate functions and GROUP BY */
SELECT
  raccoon.jay,
  raccoon.fox,
  COUNT(DISTINCT heron.beaver) AS goat,
  SUM(heron.gecko) AS horse,
  AVG(heron.gecko) AS peacock,
  MIN(heron.bison) AS rabbit,
  MAX(heron.bison) AS octopus
FROM ant AS raccoon
LEFT JOIN newt AS heron
  ON raccoon.lynx = heron.lynx
WHERE
  raccoon.finch = 'Active' AND heron.bison >= '2024-01-01'
GROUP BY
  raccoon.lynx,
  raccoon.jay,
  raccoon.fox
HAVING
  COUNT(DISTINCT heron.beaver) >= 5
ORDER BY
  horse DESC