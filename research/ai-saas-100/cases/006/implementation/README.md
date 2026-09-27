# Supplied-record enrichment component

```sh
python3 -B research/ai-saas-100/cases/006/tests/enrichment-v1/run.py
python3 -B research/ai-saas-100/cases/004/research/continuation-v1/execute_components.py 006
```

`enrichment.py` accepts JSON on stdin using the retained fixture input schema. It performs normalized exact-domain joins, field-level provider fallback, latest observation selection within each provider, exact provenance retention, and conflict reporting. Explicitly listed provider order takes precedence over recency across different providers. Equally ranked observations with the same date but different values yield null rather than arbitrary selection. Domain normalization trims whitespace, lowercases, and removes trailing dots. It does not merge www/non-www hosts or similarly named companies.

Missing values remain null. Zero employees is a supplied value, not missing. A business_summary is returned only if a source supplies that explicit field. Source text is retained as a verbatim excerpt, never passed off as a generated summary. Additional unkeyed sources remain unresolved rather than being assigned to a company. Provenance confidence is categorical and not a calibrated probability.

Python standard library only. No file access during enrichment, provider calls, external lookup, inference, or network writes. Malformed input and path/external-action requests return `invalid_input`. Only builder-visible component tests run. The 20 original inputs are reused for bounded field/provenance assertions, not counted as complete original-workflow passes.

This is not Clay, licensed-provider coverage, a generic-model benchmark, or an accepted campaign product. The frozen inference-required workflow and independent evaluation requirements remain outstanding. New research supplements the historical dossier under `research/continuation-v1/` without replacing it.
