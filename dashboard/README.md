# GVMC dashboard

A static web page for GVMC staff to view the reports collected by the PI4C bot. It has no build step and no backend of its own: the page reads the PI4C API from the browser.

## Run it

Start the API, then serve this folder:

```bash
uv run uvicorn app.main:app --reload
```

```bash
uv run python -m http.server 5500 --directory dashboard
```

Open http://localhost:5500.

## What it shows

- Headline numbers: total, open, resolved, high/critical, PwD reports, needs review, distinct problems, with photo
- A map of reports, coloured by status; larger dots are PwD reports
- Counts by status, department and issue type, plus reports per day, week or month
- A paginated report list. Click a row or map dot to see the photo, description, location and details.
- An update form for status, severity, department, note and needs-review. It only works when the server has `WRITE_ACCESS=true`; otherwise the dashboard shows **Read-only**.
- Filters for category, status, severity, department, date range (IST), PwD only and needs review. **Export CSV** downloads the filtered reports.

**GVMC area only** (on by default) limits everything to a bounding box around GVMC, from Anakapalle to Bheemunipatnam. Turn it off to see reports from anywhere.

## Settings

These are constants at the top of `app.js`:

- `API`: where the PI4C API is (`http://localhost:8000/api/v1`). Change this when the API is deployed.
- `GVMC_BBOX`, `GVMC_CENTER`: the area filter and the map's starting view.
- `PAGE_SIZE`, `AUTO_REFRESH_MS`: rows per page, and how often the data refreshes (every 2 minutes).
