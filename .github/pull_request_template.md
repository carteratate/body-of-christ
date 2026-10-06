## What changed and why

<!-- Free text. Link the issue this closes. -->

## Production safety

- [ ] No migration, or the migration is additive and its new columns are nullable or defaulted
- [ ] The API tolerates this change being absent (deploys before any migration or republish)
- [ ] No datapipeline run against live stores (Supabase or Qdrant)
- [ ] No Qdrant change

## Source checks (run locally)

<!--
Required whenever the diff touches datapipeline/. These need the gitignored
datapipeline/sources/, so CI cannot run them. Paste each output in its own
collapsed block. Otherwise replace this section's body with:
"Not applicable: this PR does not touch datapipeline/"
-->

<details><summary>Source verification: <code>python3 scripts/source_lock.py --verify</code></summary>

```
```
</details>

<details><summary>Coverage and sequence summary (0.1a): <code>cd datapipeline && python3 -m checks.report --collection &lt;name&gt;</code></summary>

<!-- Paste summary.md as Markdown, not in a code block, so its tables render. -->
</details>

<details><summary>Health summary (0.1b)</summary>

```
```
</details>

<details><summary>Release report summary (0.1c)</summary>

```
```
</details>

## About page

- [ ] This PR changes an inclusion rule or what a collection holds; the About page item is updated or ticketed

## Spec changes

<!--
Required whenever the diff touches docs/corpus-cleanup/. One line per edited spec:
the file, the item, what changed and why (docs/corpus-cleanup/README.md section 3).
Name the NEEDS-CARTER.md entries this PR answered. Otherwise write "No spec changes".
-->

## Review

<!--
Quote the fresh-context reviewer's findings and what was done about each
(docs/corpus-cleanup/README.md section 4).
-->
