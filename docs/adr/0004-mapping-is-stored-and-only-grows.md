---
status: accepted
---
# The stored mapping is the source of truth and only grows

Fake names are assigned by shuffling the word lists with a seed and handing them out in order of first appearance; the result is stored in the workspace and a name never changes once assigned. We rejected deriving each fake name from a keyed hash of the name. Hashing needs no stored state, but collisions in a small adjective-animal space need state to resolve anyway, and anyone holding the key could confirm guesses ("is `Customers` this one?"). A mapping that only grows is also what keeps obfuscated scripts stable when originals change, which the later auto-update milestone depends on.

## Consequences

- The seed reproduces a run only from an empty mapping; with an existing mapping the mapping wins.
- Values use numbered placeholders (`'text_017'`), deliberately unlike fake names, so the two cannot be confused in LLM prose.
- The mapping is as sensitive as the originals and must never be part of a bundle.
