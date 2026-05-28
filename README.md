# Breathe ESG

Breathe ESG is a prototype ESG emissions management platform that helps organizations upload, process, review, and monitor carbon emission records from multiple business data sources.

## Features

- Multi-source CSV ingestion
- Scope 1, Scope 2, Scope 3 classification
- Automated CO₂e calculations
- ESG review & approval workflow
- Record flagging and validation
- Dashboard analytics and statistics
- React frontend + Django REST backend

## Supported Data Sources

| Source | ESG Scope |
|---|---|
| SAP Fuel Data | Scope 1 |
| Utility Electricity Data | Scope 2 |
| Concur Travel Data | Scope 3 |

## Tech Stack

### Backend
- Django
- Django REST Framework
- SQLite

### Frontend
- React.js
- Axios

### Deployment
- Render

## Workflow

```text
CSV Upload
   ↓
Parsing & Validation
   ↓
CO₂e Calculation
   ↓
Scope Classification
   ↓
Review Workflow
   ↓
Dashboard Analytics

```



Current Status
Backend APIs completed
CSV ingestion implemented
Emission calculations implemented
Dashboard completed
Review workflow implemented
Deployment configured
