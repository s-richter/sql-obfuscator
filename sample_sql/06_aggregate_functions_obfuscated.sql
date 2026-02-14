/* Aggregate functions and GROUP BY */
SELECT
  moose.leopard,
  moose.dove,
  COUNT(DISTINCT kangaroo.boar) AS iguana,
  SUM(kangaroo.cheetah) AS parrot,
  AVG(kangaroo.cheetah) AS llama,
  MIN(kangaroo.kingfisher) AS hawk,
  MAX(kangaroo.kingfisher) AS coyote
FROM beaver AS moose
LEFT JOIN mouse AS kangaroo
  ON moose.pheasant = kangaroo.pheasant
WHERE
  moose.squirrel = 'Active' AND kangaroo.kingfisher >= '2024-01-01'
GROUP BY
  moose.pheasant,
  moose.leopard,
  moose.dove
HAVING
  COUNT(DISTINCT kangaroo.boar) >= 5
ORDER BY
  parrot DESC