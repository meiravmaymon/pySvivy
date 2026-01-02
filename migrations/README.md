# Database Migrations - Alembic

## Quick Reference

```bash
# Create a new migration (auto-generate from model changes)
alembic revision --autogenerate -m "description of change"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history
```

## Common Operations

### Adding a new column
```bash
alembic revision --autogenerate -m "add pdf_path to meetings"
alembic upgrade head
```

### Removing a column
```bash
alembic revision --autogenerate -m "remove obsolete column"
alembic upgrade head
```

### Rolling back
```bash
# Go back one step
alembic downgrade -1

# Go back to specific revision
alembic downgrade abc123

# Go back to beginning
alembic downgrade base
```
