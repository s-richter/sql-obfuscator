---
status: accepted
---
# Names map per part, in one case-insensitive namespace

Each part of a qualified name is mapped on its own, so `Customers`, `dbo.Customers` and `SalesDB.dbo.Customers` remain recognisably the same table after obfuscation. The same text always gets the same fake name whatever it denotes (a table and a column both called `Status` share one fake name), and `Customers` and `CUSTOMERS` are one name whose casing is carried into the fake name. This is what makes token-level renaming (ADR 0001) sufficient: the engine never needs to know what kind of thing a name is.

## Considered Options

- **Whole qualified name as one unit**: hides how many parts a reference has, but breaks the link between differently qualified references to the same object.
- **Separate namespace per kind**: reveals less when a table and a column share a name, but requires the engine to classify every name correctly, which it cannot do in unparsed procedural code.

## Consequences

- `dbo`, `sys` and `INFORMATION_SCHEMA` are on the keep-list by default.
- A stored mapping depends on this rule; changing it later invalidates existing mappings.
