# Chantier Mobile ERP

[![Django](https://img.shields.io/badge/Django-4.2+-092E20?style=for-the-badge&logo=django)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED?style=for-the-badge&logo=docker)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=for-the-badge&logo=postgresql)](https://www.postgresql.org/)

**Chantier Mobile** is a comprehensive Enterprise Resource Planning (ERP) solution designed specifically for construction site management. It streamlines operations by integrating project tracking, personnel management, financial control, material logistics, and revenue handling into a unified platform.

## 🚀 Key Features

### 🏗️ Project Management (`projects`)
- **Site Tracking**: Manage multiple construction sites with status tracking (Planning, Active, Paused, Completed).
- **Phasing**: Break down projects into distinct phases with timeline management.
- **Progress Reporting**: Track real-time progress percentages and reporting per phase.

### 👥 Personnel & HR (`personnel`)
- **Skill Management**: Catalog personnel skills and expertise.
- **Site Assignments**: Assign staff to specific sites with role definitions and daily rates.
- **Profiles**: Detailed personnel profiles linked to system users.

### 💰 Finance & Budgeting (`finance`)
- **Budget Control**: Set and monitor total budgets per site.
- **Expense Management**: diverse expense categories and approval workflows (Pending -> Approved/Rejected -> Paid).
- **Receipt Archiving**: Digital storage for expense receipts.

### 🧱 Material & Logistics (`materials`)
- **Inventory Definitions**: Standardize material units and estimated costs.
- **Request Workflow**: Streamlined material request process linking site needs to procurement.
- **Order Tracking**: Monitor status from Request to Delivery.

### 📈 Revenue & Contracts (`revenue`)
- **Contract Management**: Track client contracts, total values, and signing dates.
- **Invoicing**: Generate and track invoices with status updates (Draft, Sent, Paid, Overdue).
- **Payment Reconciliation**: Record payments via various methods (Bank Transfer, Check, Mobile Money).

## 🛠️ Tech Stack

- **Backend Framework**: Django 4.2+ (Python)
- **Database**: PostgreSQL 15
- **Task Queue**: Celery with Redis
- **Containerization**: Docker & Docker Compose
- **Authentication**: `django-allauth`

## ⚙️ Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed and running.

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd chantierMobile
   ```

2. **Environment Setup**
   Ensure you have a `.env` file in the root directory. A basic configuration is provided in `docker-compose.yml`, but for production or custom local settings, create a `.env` file:
   ```bash
   SECRET_KEY=your-secret-key
   DEBUG=1
   ALLOWED_HOSTS=127.0.0.1,localhost
   # Database settings are handled by docker-compose for local dev
   ```

3. **Build and Run**
   Start the application and all dependent services (Postgres, Redis, Celery) using Docker Compose:
   ```bash
   docker-compose up --build
   ```

4. **Access the Application**
   - Web App: [http://localhost:8001](http://localhost:8001)
   - Flower (Celery Monitoring): [http://localhost:5555](http://localhost:5555)

### Initial Setup

Once the container is running, you may need to apply migrations and create a superuser:

```bash
# Open a shell in the running container
docker-compose exec chantiermobile-service sh

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

## 📂 Project Structure

```
chantierMobile/
├── chantiermobile/      # Project configuration (settings, urls, wsgi)
├── core/                # Shared utilities and base models
├── accounts/            # User authentication and Cabinet management
├── projects/            # Site and phase management
├── personnel/           # Worker profiles and assignments
├── finance/             # Budgets and expenses
├── materials/           # Inventory and requests
├── revenue/             # Contracts and invoices
├── static/              # Static assets (CSS, JS, Images)
├── templates/           # HTML Templates
├── Dockerfile           # App container definition
└── docker-compose.yml   # Orchard service orchestration
```
