# Google Cloud Setup Instructions

This guide walks through everything you need to configure on Google Cloud for the Audio Processing Pipeline, following [project-phases.md](project-phases.md). Do these in order if you are setting up from scratch.

**Project ID:** `ask-the-elect` · **Project number:** `158822246647`. Bucket names and connection strings below use this project.

---

## Prerequisites

- A [Google Cloud project](https://console.cloud.google.com/).
- [Billing](https://console.cloud.google.com/billing) enabled (required for Cloud SQL and for Cloud Run beyond free tier).
- [Google Cloud CLI (`gcloud`)](https://cloud.google.com/sdk/docs/install) installed and authenticated:
  ```bash
  gcloud auth login
  gcloud config set project ask-the-elect
  ```

---

## 1. Enable APIs

In the Cloud Console, go to **APIs & Services → Library**, or use `gcloud`:

```bash
gcloud services enable \
  run.googleapis.com \
  storage.googleapis.com \
  sqladmin.googleapis.com \
  iap.googleapis.com
```

For Phase 5 (Spot VM worker), also enable:

```bash
gcloud services enable compute.googleapis.com
```

---

## 2. Phase 1: Cloud Run (Compute & Deployment)

### 2.1 Build and deploy

Use a **free-tier region** so the service qualifies for Cloud Run free tier: `us-central1`, `us-east1`, or `us-west1`.

**Windows:** Start **Docker Desktop** and wait until it is fully running before using `docker build` or `docker push`. If you see `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`, Docker Desktop is not running.

From the project root (where the Dockerfile is):

```bash
# Build and push to Artifact Registry (create repo if needed)
gcloud artifacts repositories create audio-pipeline --repository-format=docker --location=us-central1 2>/dev/null || true
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
docker build -t us-central1-docker.pkg.dev/ask-the-elect/audio-pipeline/app:latest .
docker push us-central1-docker.pkg.dev/ask-the-elect/audio-pipeline/app:latest

# Deploy with a strict instance cap (plan: --max-instances=5)
# Do not set PORT — Cloud Run sets it automatically (reserved).
gcloud run deploy audio-pipeline \
  --image us-central1-docker.pkg.dev/ask-the-elect/audio-pipeline/app:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --max-instances 5
```
***service url: https://audio-pipeline-158822246647.us-central1.run.app ***

Or use **Cloud Build** to build from source:

```bash
gcloud run deploy audio-pipeline \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --max-instances 5
```

After deploy, note the service URL (e.g. `https://audio-pipeline-xxxxx-uc.a.run.app`). You will use it for CORS and IAP.

---

## 3. Phase 2: GCS Upload Bucket (Media Uploads)

### 3.1 Create the bucket

Use the same region as Cloud Run when possible.

```bash
export BUCKET_UPLOADS="ask-the-elect-uploads"
gsutil mb -l us-central1 -c STANDARD gs://${BUCKET_UPLOADS}
```

### 3.2 Set CORS

Create a file `cors.json`:

```json
[
  {
    "origin": ["https://audio-pipeline-xxxxx-uc.a.run.app"],
    "method": ["PUT", "GET"],
    "responseHeader": ["Content-Type"],
    "maxAgeSeconds": 3600
  }
]
```

Replace the origin with your actual Cloud Run service URL. Do **not** include a trailing slash.

Apply CORS:

```bash
gsutil cors set cors.json gs://${BUCKET_UPLOADS}
```

### 3.3 IAM for the Cloud Run service account

Cloud Run uses a service account (default: `158822246647-compute@developer.gserviceaccount.com`). Grant it access to the upload bucket:

```bash
export RUN_SA="158822246647-compute@developer.gserviceaccount.com"
gsutil iam ch serviceAccount:${RUN_SA}:objectAdmin gs://${BUCKET_UPLOADS}
```

Or in the Console: **Cloud Storage → Bucket → Permissions → Grant access** → add the Cloud Run service account with role **Storage Object Admin** (or at least **Storage Object Creator** for uploads and **Storage Object Viewer** if you serve from this bucket).

---

## 4. Phase 5: GCS Output Bucket (Optional)

For processed WAV and job_state JSON (and for a future Spot VM worker):

```bash
export BUCKET_OUTPUTS="ask-the-elect-outputs"
gsutil mb -l us-central1 -c STANDARD gs://${BUCKET_OUTPUTS}
gsutil iam ch serviceAccount:${RUN_SA}:objectAdmin gs://${BUCKET_OUTPUTS}
```

---

## 5. Cloud SQL (Database)

### 5.1 Create a Cloud SQL instance

PostgreSQL is used by the app (e.g. for `job_state` JSON). Use a free-tier–eligible region.

```bash
gcloud sql instances create audio-pipeline-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1
```

`db-f1-micro` is the smallest (often free-tier eligible). For production you may use a larger tier.

### 5.2 Create database and user

```bash
gcloud sql databases create appdb --instance=audio-pipeline-db
gcloud sql users create appuser --instance=audio-pipeline-db --password=YOUR_SECURE_PASSWORD
```

Use a strong password and store it in Secret Manager (see below).

### 5.3 Get the connection name

```bash
gcloud sql instances describe audio-pipeline-db --format="value(connectionName)"
```

Example output: `ask-the-elect:us-central1:audio-pipeline-db`. This is `CLOUD_SQL_CONNECTION_NAME`.

### 5.4 Connect Cloud Run to Cloud SQL

When deploying (or when updating the service):

```bash
gcloud run services update audio-pipeline \
  --region us-central1 \
  --add-cloudsql-instances ask-the-elect:us-central1:audio-pipeline-db
```

The Cloud Run service account also needs the **Cloud SQL Client** role so it can connect:

```bash
gcloud projects add-iam-policy-binding ask-the-elect \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/cloudsql.client"
```

---

## 6. Secret Manager (Recommended for DB password)

Store the database password in Secret Manager and reference it from Cloud Run.

```bash
# Enable Secret Manager
gcloud services enable secretmanager.googleapis.com

# Create secret (paste password when prompted, or use --data-file)
echo -n "YOUR_SECURE_PASSWORD" | gcloud secrets create db-password --data-file=-

# Grant Cloud Run service account access to the secret
gcloud secrets add-iam-policy-binding db-password \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

When setting Cloud Run env vars, you can use **Secret Manager** in the Console: **Cloud Run → Service → Edit → Variables & Secrets → Reference a secret** and select `db-password` for `DB_PASSWORD`.

---

## 7. Cloud Run environment variables

Set these on the Cloud Run service (Console: **Edit & deploy new revision → Variables & Secrets**, or `gcloud run services update` with `--set-env-vars`).

| Variable | Required | Example / notes |
|----------|----------|------------------|
| `PORT` | Set by Cloud Run | Usually `8080` (automatic). |
| `GCS_UPLOAD_BUCKET` | Yes (for Phase 2) | `ask-the-elect-uploads` |
| `GCS_OUTPUT_BUCKET` | No (Phase 5) | `ask-the-elect-outputs` |
| `USE_CLOUD_SQL` | Yes (for Cloud SQL) | `1` |
| `CLOUD_SQL_CONNECTION_NAME` | Yes (if Cloud SQL) | `ask-the-elect:us-central1:audio-pipeline-db` |
| `DB_USER` | Yes (if Cloud SQL) | `appuser` |
| `DB_PASSWORD` | Yes (if Cloud SQL) | Use Secret Manager reference if possible. |
| `DB_NAME` | Yes (if Cloud SQL) | `appdb` |

Example (replace values; use Secret for `DB_PASSWORD` in production):

```bash
gcloud run services update audio-pipeline --region us-central1 \
  --set-env-vars "GCS_UPLOAD_BUCKET=ask-the-elect-uploads" \
  --set-env-vars "GCS_OUTPUT_BUCKET=ask-the-elect-outputs" \
  --set-env-vars "USE_CLOUD_SQL=1" \
  --set-env-vars "CLOUD_SQL_CONNECTION_NAME=ask-the-elect:us-central1:audio-pipeline-db" \
  --set-env-vars "DB_USER=appuser" \
  --set-env-vars "DB_NAME=appdb"
# Set DB_PASSWORD via Console (Secret Manager) or:
# --set-secrets "DB_PASSWORD=db-password:latest"
```

---

## 8. Phase 3: Identity-Aware Proxy (IAP)

1. In **Cloud Run**, open your service → **Security** tab.
2. Under **Authentication**, set to **Require authentication**.
3. Choose **Identity-Aware Proxy (IAP)** when prompted.
4. In **APIs & Services → OAuth consent screen**, configure the consent screen (Internal or External) and add an app name if needed.
5. In **Security → Identity-Aware Proxy**, find the Cloud Run app and **Add principal** → add the Google accounts that may access the app → assign role **IAP-secured Web App User**.

Only those principals can open the Cloud Run URL; unauthenticated users are blocked before reaching the app.

---

## 9. Phase 4: Billing budget and alerts

1. Go to **Billing → Budgets & alerts**.
2. **Create budget** (e.g. name: “Audio Pipeline”, amount: **$5**).
3. Set alerts at **50%**, **90%**, and **100%** of the budget (actual and/or forecasted).
4. Add **Email** (and optionally other channels) for notifications.

---

## 10. Local development

- Run the app with **SQLite** and **local uploads** by default (no GCP env vars).
- To test Cloud SQL locally: set `USE_CLOUD_SQL=1` and the Cloud SQL vars; use the [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy) and Application Default Credentials:
  ```bash
  gcloud auth application-default login
  cloud_sql_proxy -instances=ask-the-elect:us-central1:audio-pipeline-db=tcp:5432
  ```
  Then set `CLOUD_SQL_CONNECTION_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` and point the app at `localhost:5432` (or use the connector, which works with ADC).
- To test GCS uploads locally: set `GCS_UPLOAD_BUCKET` and use `gcloud auth application-default login` so the app can generate signed URLs and access GCS.

---

## 11. Phase 5: Spot VM worker (high level)

When you add a Spot VM worker that processes the queue:

- Use the **same** GCS upload bucket as input and the **output bucket** for WAV and job_state JSON.
- Ensure the VM’s service account has **Storage Object Admin** (or appropriate read/write) on both buckets and **Cloud SQL Client** so it can connect to the same Cloud SQL instance.
- The worker script should: poll Cloud SQL (or a queue table) for the next job, download the media from GCS to a temp path, run the pipeline, upload WAV and optional job_state JSON to GCS, and update Cloud SQL. No persistent local state.

Detailed Spot VM setup (instance template, startup script, IAM) is outside this doc; the app and storage are already built to support this pattern.

---

## Quick reference: URLs and IDs

| Item | Where to find it |
|------|------------------|
| Project ID | `ask-the-elect` |
| Project number | `158822246647` (use for RUN_SA: `158822246647-compute@developer.gserviceaccount.com`) |
| Cloud Run URL | Cloud Run → your service → URL |
| Cloud Run service account | Cloud Run → Service → Security → Service account |
| Cloud SQL connection name | `gcloud sql instances describe INSTANCE --format="value(connectionName)"` |

---

## Troubleshooting

### Container failed to start and listen on PORT

If a revision fails with *"The user-provided container failed to start and listen on the port defined by PORT=8080 within the allocated timeout"*:

- The app defers DB/ffmpeg/queue init to a background thread so the server binds to `PORT` immediately. Redeploy with the latest code.
- If the instance still fails (e.g. very slow Cold SQL connection), increase the **Startup CPU boost** and/or the **Initialization timeout** in Cloud Run: **Edit & deploy new revision → Container(s) → Advanced settings** — set **Initialization timeout** (e.g. 300s). You can also raise **Maximum number of instances** so more instances can be initializing.

---

## Checklist

- [ ] APIs enabled (Run, Storage, SQL Admin, IAP; Compute if using Spot)
- [ ] Cloud Run deployed in a free-tier region with `--max-instances=5`
- [ ] GCS upload bucket created; CORS set; Cloud Run SA has object access
- [ ] GCS output bucket created (optional); Cloud Run SA has object access
- [ ] Cloud SQL instance and database created; user and password set
- [ ] Cloud Run connected to Cloud SQL; SA has `cloudsql.client`
- [ ] Env vars set on Cloud Run (buckets, `USE_CLOUD_SQL`, DB vars)
- [ ] DB password in Secret Manager and referenced in Cloud Run (recommended)
- [ ] IAP enabled and users granted **IAP-secured Web App User**
- [ ] Billing budget ($5) and alerts (50%, 90%, 100%) configured
