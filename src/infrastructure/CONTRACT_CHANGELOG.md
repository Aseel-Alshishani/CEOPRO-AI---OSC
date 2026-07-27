# CEOPRO AI - Infrastructure Contract Changelog

All breaking changes, database constraint adjustments, and API/Event contract modifications between Web-App, Ingestion, and AI/ML teams are strictly tracked here.

## - 2026-07-27
### Added
- Initialized core relational multi-tenancy database schema (`init_schema.sql`).
- Added critical `product_scores` and `campaigns` production tables to database configuration.
- Deployed live asynchronous message broker streaming topics inside Redis (`init_broker.py`).
- Integrated strict `X-Internal-Service-Token` middleware authentication policy (`security.py`).
- Configured automated multi-tenant raw ingestion sample files under `/mocks`.
