# Spot Reconciler

> **Status: IMPLEMENTED** | Last verified: 2026-03-08 | Legacy design

Legacy discovery job that merged sitemap and taxonomy data, detected spot changes via SHA256 checksums, and maintained a state snapshot for incremental updates.

**Package path:** `packages/jobs/spot_reconciler`

This package reflects the earlier discovery design. The target architecture described in the docs now replaces it with three planned processors:

- `discovery_diff`
- `spot_report_processor`
- `catalog_builder`

See [Discovery Processors](discovery-processors.md) for the planned replacement model and [Taxonomy Scraper](../scrapers/taxonomy-scraper.md) for the legacy context.
