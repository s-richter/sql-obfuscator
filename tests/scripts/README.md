# SQL test scripts

Every script here is run through every check the project has. All names and values are
invented. The scripts are compared byte for byte, so git is told not to touch their line
endings (see `.gitattributes`).

Scripts 01 to 28 come from the earlier version of this tool. Scripts 30 and up were written
for this one, each aimed at a construct the earlier scripts do not cover.

## T-SQL (34 scripts)

| Script | Lines | Source | Covers |
|---|---|---|---|
| `01_simple_select.sql` | 6 | earlier tool | Simple select (basic). |
| `02_joins.sql` | 15 | earlier tool | Joins (basic). |
| `03_cte_example.sql` | 27 | earlier tool | CTE example (basic). |
| `04_temporary_tables.sql` | 28 | earlier tool | Temporary tables (basic). |
| `05_dml_operations.sql` | 23 | earlier tool | DML operations (basic). |
| `06_aggregate_functions.sql` | 16 | earlier tool | Aggregate functions (basic). |
| `07_multiple_batches.sql` | 45 | earlier tool | Multiple batches (basic). |
| `08_schema_qualified.sql` | 20 | earlier tool | Schema qualified (basic). |
| `09_tsql_advanced_temp_cte.sql` | 101 | earlier tool | Temp cte (advanced). |
| `10_tsql_advanced_multi_step.sql` | 102 | earlier tool | Multi step (advanced). |
| `13_tsql_extreme_operational_workflow.sql` | 510 | earlier tool | Operational workflow (extreme). |
| `14_tsql_extreme_financial_reconciliation.sql` | 539 | earlier tool | Financial reconciliation (extreme). |
| `15_tsql_extreme_supply_chain_resilience.sql` | 837 | earlier tool | Supply chain resilience (extreme). |
| `16_tsql_extreme_manufacturing_control_tower.sql` | 843 | earlier tool | Manufacturing control tower (extreme). |
| `17_tsql_extreme_energy_grid_balancing.sql` | 809 | earlier tool | Energy grid balancing (extreme). |
| `18_tsql_extreme_portfolio_liquidity_command_center.sql` | 770 | earlier tool | Portfolio liquidity command center (extreme). |
| `19_tsql_extreme_collateral_mobility_command.sql` | 789 | earlier tool | Collateral mobility command (extreme). |
| `20_tsql_extreme_trade_surveillance_fusion.sql` | 793 | earlier tool | Trade surveillance fusion (extreme). |
| `21_tsql_extreme_clearing_liquidity_orchestrator.sql` | 780 | earlier tool | Clearing liquidity orchestrator (extreme). |
| `30_tsql_bracketed_names.sql` | 15 | new | Bracketed and double-quoted names: spaces, reserved words, `]]` inside a name. |
| `31_tsql_case_variants.sql` | 14 | new | The same names in different casing. |
| `32_tsql_qualified_names.sql` | 14 | new | One table referenced with one to four name parts; `sys` and `INFORMATION_SCHEMA`. |
| `33_tsql_trigger.sql` | 28 | new | `CREATE TRIGGER` with `inserted` and `deleted`. |
| `34_tsql_functions.sql` | 39 | new | Scalar, inline and multi-statement functions; `CROSS APPLY`. |
| `35_tsql_procedural_without_semicolons.sql` | 56 | new | Procedure with `IF` without `BEGIN`, cursor, `TRY/CATCH`, `THROW`, no semicolons. Everything sqlglot's parser rejects or rewrites. |
| `36_tsql_merge_pivot_window.sql` | 44 | new | `MERGE` with `OUTPUT $action`, `PIVOT`, `UNPIVOT`, window functions, `OFFSET/FETCH`, `OPTION`. |
| `37_tsql_literals.sql` | 41 | new | Every kind of value: escaped quotes, empty and punctuation-only strings, comment-like strings, hex, money, scientific notation, numbers on both sides of the number rule. |
| `38_tsql_comments.sql` | 17 | new | Line, block, nested and empty comments; comment-like strings; no newline at end of file. |
| `39_tsql_batches_and_commands.sql` | 34 | new | `GO`, `GO 5`, lowercase `go`, `PRINT`, `FETCH`, `USE`, `SET` without semicolons: the words that trigger sqlglot's command mode. |
| `40_tsql_poorly_formatted.sql` | 6 | new | Valid but badly formatted: one-line statements, missing spaces, tabs, lowercase keywords. |
| `41_tsql_variables_and_system_objects.sql` | 35 | new | Table variables, `@@` system variables, temp and global temp tables, `sys` catalog views, table hints, `EXEC` with named arguments. |
| `42_tsql_ddl.sql` | 44 | new | Schema, table with constraints and computed column, filtered index, `ALTER`, view, `GRANT`/`DENY`. |
| `43_tsql_windows_line_endings.sql` | 6 | new | CRLF line endings, including inside a string. |
| `44_tsql_unicode_with_bom.sql` | 3 | new | UTF-8 byte order mark; non-ASCII names, strings and comment. |

## Hive (15 scripts)

| Script | Lines | Source | Covers |
|---|---|---|---|
| `11_hive_advanced_partition_window.sql` | 68 | earlier tool | Partition window (advanced). |
| `12_hive_advanced_nested_queries.sql` | 96 | earlier tool | Nested queries (advanced). |
| `22_hive_extreme_lakehouse_quality_mesh.sql` | 160 | earlier tool | Lakehouse quality mesh (extreme). |
| `23_hive_extreme_marketing_attribution_graph.sql` | 130 | earlier tool | Marketing attribution graph (extreme). |
| `24_hive_extreme_subscription_revenue_waterfall.sql` | 139 | earlier tool | Subscription revenue waterfall (extreme). |
| `25_hive_extreme_federated_risk_signal_fabric.sql` | 407 | earlier tool | Federated risk signal fabric (extreme). |
| `26_hive_extreme_cross_border_compliance_mesh.sql` | 469 | earlier tool | Cross border compliance mesh (extreme). |
| `27_hive_extreme_telemetry_anomaly_fabric.sql` | 550 | earlier tool | Telemetry anomaly fabric (extreme). |
| `28_hive_extreme_marketplace_fraud_resolution_mesh.sql` | 617 | earlier tool | Marketplace fraud resolution mesh (extreme). |
| `50_hive_ddl_storage.sql` | 39 | new | External table, complex column types, SerDe and format class names, `LOCATION`, `TBLPROPERTIES`, CTAS. |
| `51_hive_backticks_and_case.sql` | 12 | new | Backtick-quoted names, reserved words as names, mixed casing. |
| `52_hive_complex_types.sql` | 23 | new | Map, array and struct access, `LATERAL VIEW`, JSON functions, `named_struct`. |
| `53_hive_settings_and_commands.sql` | 21 | new | `SET` keys, `USE`, `MSCK REPAIR`, `SHOW`, `DESCRIBE`, `ANALYZE`, `ADD JAR`, temporary function: several trigger sqlglot's command mode. |
| `54_hive_insert_and_distribution.sql` | 34 | new | Multi-insert, `INSERT OVERWRITE DIRECTORY`, a `/*+ MAPJOIN */` hint, `DISTRIBUTE BY`, `TABLESAMPLE`, `TRANSFORM`. |
| `55_hive_literals_and_comments.sql` | 27 | new | Both quote styles, backslash escapes, numeric suffixes (`100L`), typed literals, comments. |

## Scripts that go beyond the stated rules

Scripts 13 to 21 each build one dynamic pivot query inside strings. Real target scripts do
not do this. The scripts stay because they prove that names inside strings cannot leak: the
whole string becomes a placeholder.

## Hazards these scripts exposed

Found while writing the scripts, before any engine code existed. Each one needs handling in
the milestone named.

| Hazard | Script | Milestone |
|---|---|---|
| A file can start with a byte order mark and use CRLF line endings; both must survive a round-trip. | 43, 44 | 1 |
| A money value such as `$1250.75` is tokenized as a name `$1250`, a dot and a number `75`. | 37 | 1 |
| `$action` and the `inserted`/`deleted` tables are tokenized as ordinary names and belong on the keep-list. | 33, 36 | 1 |
| A Hive hint such as `/*+ MAPJOIN(b) */` is one token. A name inside it would not be replaced unless the hint is tokenized separately. This would be a leak. | 54 | 2 |
| Hive numeric suffixes (`100L`, `10Y`, `3.14BD`) produce extra tokens that overlap the number in the source text. | 55 | 2 |
| Hive `SET` keys and `ADD JAR` paths are tokenized as names, so they are replaced unless handled specially. | 53 | 2 |

## Adding a script

Put it in the folder for its dialect, give it the next free number, and add a row to the
table above. A test fails if a script is missing from this page.
