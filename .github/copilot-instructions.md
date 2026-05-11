# CamillaDataset Migration Project - AI Agent Guide

## Project Overview
This is a **NocoDB → Baserow migration tool** for the CamillaDataset, a research database about oil exploration with complex many-to-many relationships between entities, people, roles, licenses, infrastructure, and events.

## Architecture Pattern: Two-Phase Migration

### Phase 1: Extract (getData.py)
- Fetches data from NocoDB API with pagination
- Saves raw JSON with `_nc_m2m_*` relationship tables intact
- Located in `data/JSON/` directory

### Phase 2: Transform & Load (putData.py)
Uses a **three-pass import strategy** to handle circular dependencies:
1. **Core data import**: Creates records with basic fields (no relationships)
2. **Relationship population**: Updates records with link fields using ID mappings
3. **Second-pass updates**: Special tables like `Entity_Concessions_Update` handle circular dependencies

## Critical Workflow Commands

```bash
# Extract from NocoDB (requires tables.csv with table_name,table_id pairs)
python3 getData.py

# Create Baserow table structure (run once, requires JWT authentication)
python3 components/create_tables.py

# Migrate data with relationship handling
python3 putData.py --clear              # Full migration, clears existing data
python3 putData.py --table Entity       # Single table migration
python3 putData.py --dry-run            # Preview without changes
```

## Environment Configuration
Requires `.env` file with:
- `NOCODB_BASE_URL` and `NOCODB_TOKEN` (for getData.py)
- `BASEROW_BASE_URL`, `DATABASE_ID`, `API_TOKEN` (for data operations)
- `USER_EMAIL`, `USER_PASSWORD` (for JWT token - structural operations only)

**Important**: API tokens are for data CRUD; JWT tokens are for creating tables/fields.

## Key Architectural Decisions

### 1. Import Order Matters (putData.py lines 149-172)
Tables import in dependency order to ensure foreign keys exist:
```python
Phase 1: Location, Source
Phase 2: Entity, People, Role (Entity must precede Role)
Phase 3: Licenses (must follow Entity for granted_to/granted_by)
Phase 7: Entity_Concessions_Update (circular dependency resolution)
```

**Why**: Baserow link fields require target records to exist. Wrong order = silent relationship failures.

### 2. Relationship Mapping Pattern (putData.py lines 643-937)
NocoDB `_nc_m2m_*` junction tables map to Baserow link fields:
```python
'_nc_m2m_role_entities': {
    'field_name': 'linked_entities',  # Baserow field name
    'source_table': 'Entity',          # Where to lookup IDs
    'id_field': 'entity_id'            # Which ID to extract from junction
}
```

### 3. Circular Dependency Pattern (Entity ↔ Licenses)
Problem: Entity needs Licenses IDs, Licenses needs Entity IDs.
Solution: Import Entity twice:
- First pass: Create Entity with basic data
- Import Licenses: Links to Entity 
- Second pass (`Entity_Concessions_Update`): Updates Entity with Licenses links

**Implementation**: Check `is_update_only` flag in `import_table_data()` (line 1038+)

**CRITICAL**: Update-only tables (ending in `_Update`) must NEVER trigger `clear_table`, or they'll delete existing records instead of updating them. The check `if clear_table and not dry_run and not is_update_only` prevents this.

### 4. ID Mapping System
`self.id_mappings` dictionary tracks NocoDB ID → Baserow ID conversions:
```python
self.id_mappings['Entity'][67] = 1234  # NocoDB ID 67 → Baserow ID 1234
```
Used during relationship resolution to translate junction table IDs.

## Project-Specific Conventions

### Field Naming
- NocoDB: `entity_type (past)`, `start-date` (mixed conventions)
- Baserow: `entity_type_past`, `start_date` (snake_case, no symbols)
- Mapping defined in `create_field_mapping()` (putData.py lines 425-525)

### Relationship Field Naming
- `linked_*` prefix for most relationships: `linked_people`, `linked_entities`
- Exception: `granted_to`/`granted_by` (Licenses ↔ Entity)
- Exception: `concessions_grantee`/`concessions_granter` (Entity reverse links)

### Date Normalization
All dates convert to `YYYY-MM-DD`:
- `1961` → `1961-01-01` (year only)
- `2025-04-18T10:30:00+00:00` → `2025-04-18` (ISO datetime)

## Common Debugging Scenarios

### Empty Link Fields After Migration
**Check**: Import order. Does source table import before target table?
**Check**: ID mappings exist in `self.id_mappings` for source table.
**Check**: Relationship mapping defined for this `_nc_m2m_*` junction table.
**Debug**: Add print statements in `map_relationships_to_baserow()` to see if `new_ids` is populated.

### "Field not found" Errors
**Cause**: Mismatch between `create_tables.py` field definitions and `putData.py` field mappings.
**Fix**: Run `ensure_relationship_fields()` or manually create missing link field with JWT token.

### Rate Limiting
BaserowClient has built-in `rate_limit_delay=0.1` seconds between requests. Increase if hitting 429 errors.

## File Organization

```
components/
  ├── baserow_client.py       # API wrapper with rate limiting
  ├── create_tables.py         # Table structure creation (run once)
  └── data_transformer.py      # Data validation (currently minimal use)

data/JSON/                     # Extracted NocoDB data
  ├── Entity_data.json
  ├── Licenses_data.json
  └── ...

putData.py                     # Main migration orchestrator (1200+ lines)
getData.py                     # NocoDB extraction script
```

## Testing Strategy
No formal tests. Validation is manual:
1. Run with `--dry-run` to preview
2. Migrate single table: `--table Location`
3. Check record counts in Baserow UI match JSON file counts
4. Verify link fields populated (check Entity 176 has license links)

## Known Limitations
- Some license records (IDs 2, 3, 4, 38-42, 46) missing from export → relationships to them silently fail
- No rollback mechanism - use `--clear` to restart
- Relationship updates don't create Baserow "reverse links" automatically via API (both sides must be populated)
