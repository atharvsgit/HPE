# Data Validity Checker

Enterprise Data Quality and Observability Platform Frontend

## Features

- Multi-source data ingestion (CSV, DB, API, Cloud)
- Schema detection
- Dynamic rule builder
- Validation engine (local + API-ready)
- Observability dashboard (charts + tables)
- Dataset lifecycle management

## Tech Stack

- React.js
- TailwindCSS
- Chart.js
- Axios

## How to Run

```bash
npm install
npm run dev
```

## Folder Structure

The project is organized into a modular React SPA structure:

- `src/components/ingestion`: source selection, file upload, database/API/cloud forms, schema table
- `src/components/ruleBuilder`: rule authoring and validation results UI
- `src/components/dashboard`: health, anomaly, drift, and failure visualizations
- `src/components/common`: shared UI utilities such as loaders, toasts, modals, and badges
- `src/pages`: route-level pages for ingestion, rules, and dashboard
- `src/services`: Axios client, endpoint wrappers, and local profiling/derived-metrics utilities
- `src/context`: shared dataset state across ingestion, rule building, and observability
- `src/assets`: visual assets for the application shell

## Scripts

- `npm run dev`: start the local development server
- `npm run build`: create a production build
- `npm run preview`: preview the production build locally
