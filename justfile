# ChantierMobile Justfile
# A command runner for development, deployment, and maintenance tasks
# Usage: just <command>

# Default recipe - shows available commands
default:
    @just --list

# =============================================================================
# DEVELOPMENT COMMANDS
# =============================================================================

# Start all development services
dev-up:
    docker-compose up -d
    @echo "🚀 Development services started"
    @echo "📊 Django: http://localhost:8001"
    @echo "🗄️  PostgreSQL: localhost:5432"
    @echo "🔴 Redis: localhost:6379"

# Stop all development services
dev-down:
    docker-compose down
    @echo "🛑 Development services stopped"

# Restart all development services
dev-restart:
    docker-compose restart
    @echo "🔄 Development services restarted"

# View development service logs
dev-logs service="chantiermobile-service":
    docker-compose logs -f {{service}}

# View all development service logs
dev-logs-all:
    docker-compose logs -f

# =============================================================================
# DJANGO MANAGEMENT COMMANDS
# =============================================================================

# Run Django system checks
check:
    docker-compose exec chantiermobile-service python manage.py check

# Run Django migrations
migrate:
    docker-compose exec chantiermobile-service python manage.py migrate
    @echo "✅ Migrations applied"

# Create new Django migration
makemigrations message="":
    docker-compose exec chantiermobile-service python manage.py makemigrations {{message}}

# Create Django superuser
createsuperuser:
    docker-compose exec chantiermobile-service python manage.py createsuperuser

# Open Django shell
shell:
    docker-compose exec chantiermobile-service python manage.py shell

# =============================================================================
# INTERNATIONALIZATION COMMANDS
# =============================================================================

# Generate translation files for all languages
i18n-extract:
    docker-compose exec chantiermobile-service python manage.py makemessages -l fr
    docker-compose exec chantiermobile-service python manage.py makemessages -l en
    @echo "📝 Translation files generated"

# Compile translation files
i18n-compile:
    docker-compose exec chantiermobile-service python manage.py compilemessages
    @echo "🔧 Translation files compiled"

# Update all translations (extract + compile)
i18n-update: i18n-extract i18n-compile
    @echo "🌐 Internationalization updated"

# =============================================================================
# DATABASE COMMANDS
# =============================================================================

# Create database backup
db-backup filename="backup_$(date +%Y%m%d_%H%M%S).sql":
    docker-compose exec tictacflow-postgres-service pg_dump -U postgres chantiermobile_db > {{filename}}
    @echo "💾 Database backed up to {{filename}}"

# Restore database from backup
db-restore filename:
    docker-compose exec -T tictacflow-postgres-service psql -U postgres chantiermobile_db < {{filename}}
    @echo "📥 Database restored from {{filename}}"

# Reset database (WARNING: destroys all data)
db-reset:
    @echo "⚠️  This will delete all data. Are you sure? (y/N)"
    @read -r confirm && [ "$$confirm" = "y" ] || exit 1
    docker-compose down
    docker volume rm chantiermobile_postgres_data || true
    docker-compose up -d tictacflow-postgres-service
    sleep 5
    docker-compose exec chantiermobile-service python manage.py migrate
    @echo "🗑️  Database reset complete"

# =============================================================================
# TESTING COMMANDS
# =============================================================================

# Run all tests
test:
    docker-compose exec chantiermobile-service pytest

# Run tests with coverage
test-coverage:
    docker-compose exec chantiermobile-service pytest --cov=. --cov-report=html --cov-report=term

# Run specific test file
test-file file:
    docker-compose exec chantiermobile-service pytest {{file}}

# Run tests for specific app
test-app app:
    docker-compose exec chantiermobile-service pytest tests/ -k "{{app}}"

# Run unit tests only
test-unit:
    docker-compose exec chantiermobile-service pytest -m unit

# Run integration tests only
test-integration:
    docker-compose exec chantiermobile-service pytest -m integration

# Run end-to-end tests only
test-e2e:
    docker-compose exec chantiermobile-service pytest -m e2e

# Run API tests only
test-api:
    docker-compose exec chantiermobile-service pytest -m api

# Run performance tests only
test-performance:
    docker-compose exec chantiermobile-service pytest -m performance

# Run tests with verbose output
test-verbose:
    docker-compose exec chantiermobile-service pytest -v

# Run tests in parallel
test-parallel:
    docker-compose exec chantiermobile-service pytest -n auto

# Run tests and stop on first failure
test-fast:
    docker-compose exec chantiermobile-service pytest -x

# Run tests with debugging
test-debug:
    docker-compose exec chantiermobile-service pytest -v -s --pdb

# Install test dependencies
test-install:
    docker-compose exec chantiermobile-service pip install -r requirements-test.txt

# Generate coverage report
test-coverage-report:
    docker-compose exec chantiermobile-service pytest --cov=. --cov-report=html
    @echo "Coverage report generated in htmlcov/"

# Watch for changes and run tests
test-watch:
    docker-compose exec chantiermobile-service pytest --watch

# Run tests with specific marker
test-marker marker:
    docker-compose exec chantiermobile-service pytest -m {{marker}}

# Run tests for specific module
test-module module:
    docker-compose exec chantiermobile-service pytest tests/test_{{module}}.py

# =============================================================================
# CODE QUALITY COMMANDS
# =============================================================================

# Format Python code with black
format:
    docker-compose exec chantiermobile-service black .

# Lint Python code with flake8
lint:
    docker-compose exec chantiermobile-service flake8 .

# Sort imports with isort
sort-imports:
    docker-compose exec chantiermobile-service isort .

# Run all code quality checks
quality: format sort-imports lint
    @echo "✨ Code quality checks complete"

# =============================================================================
# DEPLOYMENT COMMANDS
# =============================================================================

# Build production images
build:
    docker-compose -f docker-compose.prod.yml build

# Deploy to production
deploy:
    docker-compose -f docker-compose.prod.yml up -d
    @echo "🚀 Production deployment complete"

# View production logs
prod-logs service="chantiermobile-service":
    docker-compose -f docker-compose.prod.yml logs -f {{service}}

# =============================================================================
# MONITORING COMMANDS
# =============================================================================

# Show service status
status:
    docker-compose ps
    @echo ""
    @echo "📊 Service URLs:"
    @echo "Django: http://localhost:8001"
    @echo "PostgreSQL: localhost:5432"
    @echo "Redis: localhost:6379"

# Show resource usage
stats:
    docker stats --no-stream

# Clean up unused Docker resources
cleanup:
    docker system prune -f
    docker volume prune -f
    @echo "🧹 Docker cleanup complete"

# =============================================================================
# UTILITIES
# =============================================================================

# Install Python dependencies
install-deps:
    docker-compose exec chantiermobile-service pip install -r requirements.txt

# Update Python dependencies
update-deps:
    docker-compose exec chantiermobile-service pip install --upgrade -r requirements.txt

# Generate requirements.txt from current environment
freeze-deps:
    docker-compose exec chantiermobile-service pip freeze > requirements.txt
    @echo "📦 Requirements frozen"

# Show Django version
version:
    docker-compose exec chantiermobile-service python --version
    docker-compose exec chantiermobile-service python -c "import django; print(f'Django: {django.VERSION}')"

# =============================================================================
# MAINTENANCE COMMANDS
# =============================================================================

# Clear Django cache
clear-cache:
    docker-compose exec chantiermobile-service python manage.py clearcache
    @echo "🗑️  Cache cleared"

# Collect static files
collectstatic:
    docker-compose exec chantiermobile-service python manage.py collectstatic --noinput
    @echo "📁 Static files collected"

# Create database backup with timestamp
backup: db-backup

# Full system health check
health: check status
    @echo "🏥 System health check complete"

# =============================================================================
# DEVELOPMENT WORKFLOWS
# =============================================================================

# Setup new development environment
setup: dev-up migrate createsuperuser
    @echo "🛠️  Development environment setup complete"
    @echo "📊 Django: http://localhost:8001"
    @echo "👤 Create superuser: just createsuperuser"

# Quick restart during development
quick-restart: dev-down dev-up
    @echo "⚡ Quick restart complete"

# Prepare for deployment
deploy-prepare: test quality i18n-update collectstatic
    @echo "🚀 Ready for deployment"

# =============================================================================
# DATA MANAGEMENT
# =============================================================================

# Load sample data (if available)
load-sample-data:
    docker-compose exec chantiermobile-service python manage.py loaddata sample_data.json || echo "No sample data file found"

# Create data backup fixture
create-fixture app model:
    docker-compose exec chantiermobile-service python manage.py dumpdata {{app}}.{{model}} --indent 2 > {{app}}_{{model}}_fixture.json
    @echo "📄 Fixture created: {{app}}_{{model}}_fixture.json"

# =============================================================================
# SECURITY COMMANDS
# =============================================================================

# Check for security vulnerabilities
security-check:
    docker-compose exec chantiermobile-service pip install safety
    docker-compose exec chantiermobile-service safety check
    @echo "🔒 Security check complete"

# Update dependencies for security
security-update:
    docker-compose exec chantiermobile-service pip install --upgrade pip
    docker-compose exec chantiermobile-service pip install --upgrade safety
    docker-compose exec chantiermobile-service safety check --update
    @echo "🔒 Security updates applied"

# =============================================================================
# CUSTOM ALIASES
# =============================================================================

# Quick aliases for common tasks
up: dev-up
down: dev-down
restart: dev-restart
logs: dev-logs
test-all: test
migrate-all: migrate
shell-django: shell
