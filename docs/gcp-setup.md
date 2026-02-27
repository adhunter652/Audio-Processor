414# Google Cloud Setup Instructions0=============================3e
-+=-+
 ed4r-xrrrrrrrrrrrrrrrrrrrrrrrrd+
 --------------------- -e4 ec 

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

From the project root (where the Dockerfile is). *If you use the Cloud Build trigger (Section 2.2), you can skip the Artifact Registry steps.*

```bash
# Optional: build and push to Artifact Registry (create repo if needed)
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

### 2.2 Deploy from GitHub (Cloud Build trigger)

Connect your GitHub repo to Cloud Run so each push to `main` builds and deploys automatically. Cloud Build builds the image from your repo and deploys to Cloud Run; you don't create or push to Artifact Registry yourself.

1. In **Cloud Build** → **Triggers**, connect your GitHub repo (first-time: **Connect repository**).
2. **Create trigger**: name e.g. `deploy-audio-pipeline`, event **Push to a branch**, branch `^main$`.
3. **Configuration**:
   - **Cloud Run**: set **Service** to `audio-pipeline`, **Region** to `us-central1`, **Source** = repo root. If you set a **Service account** under Advanced, you must set **Logging** to **Cloud Logging only** (see **Troubleshooting** below if the build fails with a `service_account` / `logs_bucket` error).
   - **Or** use **Build configuration file** with path `cloudbuild.yaml` (repo root). The repo’s `cloudbuild.yaml` sets the required logging option for custom service accounts.
4. Ensure the Artifact Registry repo exists (once per project): `gcloud artifacts repositories create audio-pipeline --repository-format=docker --location=us-central1` (ignore if it already exists).
5. If the trigger uses a **custom service account** (e.g. `github-deploy@...`), grant it permission to push images: **Artifact Registry Writer** and **Logs Writer** (see **Troubleshooting** for the exact `gcloud` commands if the build fails with permission errors).
6. Save. Each push to `main` will build and deploy.

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

**IAP requirements:** The project must be inside a **Google Cloud organization**, and every user you add must belong to that **same organization** (e.g. same Google Workspace or Cloud Identity domain). Personal Gmail/consumer accounts or users from another org will get *"do not belong to a permitted customer"*. If your project is a personal project (no organization), use the **Cloud Run Invoker** option at the end of this section instead of IAP.

1. In **Cloud Run**, open your service → **Security** tab.
2. Under **Authentication**, set to **Require authentication**.
3. Choose **Identity-Aware Proxy (IAP)** when prompted.
4. In **APIs & Services → OAuth consent screen**, configure the consent screen (Internal or External) and add an app name if needed.
5. **Add users who may access the app** (this is done from Cloud Run, not from the IAP page):
   - Stay in **Cloud Run** → your service → **Security** tab.
   - Under **IAP**, click **Edit policy**.
   - Add one or more principals (e.g. `user:you@your-org.com`) — only accounts in your **same organization** — and optionally the access level required.
   - Click **Save**.

Only those principals can open the Cloud Run URL; unauthenticated users are blocked before reaching the app.

**Alternative if IAP is not an option (no organization or mixed identities):** Use **Require authentication** but **do not** select IAP. Then grant access via IAM using the Permissions panel (see below) and assign role **Cloud Run Invoker**. Any Google account (including personal) that has `roles/run.invoker` on the service can open the URL after signing in with that Google account.

**Where to find Permissions for a Cloud Run service:** The Permissions (IAM) panel is in the **right-hand info panel**, not in the main service tabs. (1) Go to [Cloud Run](https://console.cloud.google.com/run/). (2) **Check the checkbox** next to your service name (do not click the service name itself, or you only see Revisions, Metrics, Logs, Security). (3) On the **right side**, open the info panel—if you don’t see it, click **Show Info Panel** or the panel icon. (4) In that panel, open the **Permissions** tab. (5) Click **Grant access** (or **Add principal**), enter the user’s email (e.g. `user@allowed-domain.com`), choose role **Cloud Run Invoker**, and save. If the right panel still doesn’t show Permissions, use the CLI: `gcloud run services add-iam-policy-binding SERVICE_NAME --region=REGION --member="user:EMAIL" --role="roles/run.invoker"`.

**Can users request access through Google?** Google Cloud does **not** provide a built-in “request access” flow where an unlisted user can ask for permission and an admin approves it from the console. Access is always granted by an admin (or by automation). To let users request access, use one of these approaches:

- **Manual process:** Publish a link to a [Google Form](https://forms.google.com) (or similar) where users submit their email and reason; the form notifies you by email. When you approve, add them via the **Permissions** panel (see “Where to find Permissions” above: select the service with the checkbox → right-hand panel → Permissions → Grant access → Cloud Run Invoker) or via IAP (Security tab → IAP → Edit policy). Only principals from an allowed domain can be added if your org has Domain Restricted Sharing.
 **Google Group:** If your org uses Google Groups, grant **Cloud Run Invoker** (or IAP access) to a group (e.g. `audio-pipeline-users@yourdomain.com`). Users request to join the group through your normal process; once they’re in the group, they can use the service without you editing IAM each time.
- **Custom app:** Build a small “request access” page that accepts the user’s email, stores it (e.g. Firestore or Cloud SQL), and notifies an admin or creates a ticket. The admin adds the user in IAM when they approve. This is custom logic, not a Google-managed feature.

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

### IAP: "One or more users named in the policy do not belong to a permitted customer"

IAP for Cloud Run only allows identities from the **same Google Cloud organization** as the project. If you see this when adding a user:

- **Personal / consumer accounts** (e.g. `@gmail.com`) or accounts from another organization cannot be added to the IAP policy.
- **Fix options:**
  1. **Use only org accounts:** Add only users whose Google accounts belong to your organization (same Workspace or Cloud Identity domain).
  2. **Switch to Cloud Run Invoker (no IAP):** If the project has no organization or you need to allow personal accounts:
     - In **Cloud Run** → your service → **Security**, set authentication to **Require authentication** but **do not** choose IAP (or switch back to the non-IAP option if you already enabled IAP).
     - Go to **Permissions** → **Grant access** and add each user (e.g. `user:friend@gmail.com`) with role **Cloud Run Invoker**.
     - Those users can then open the service URL and sign in with their Google account; no organization required.
     - **Note:** If your project is in an organization with **Domain Restricted Sharing** (see next entry), you can only add principals from allowed domains.

### IAM: "Domain Restricted Sharing" — only principals in allowed domains can be added

Your Google Cloud **organization** has the policy `constraints/iam.allowedPolicyMemberDomains` enabled. That means you can only add IAM principals (users, groups) whose email addresses are in the **allowed domains** list (e.g. your company domain like `@yourcompany.com`). Adding `@gmail.com` or another disallowed domain will fail.

- **What to do:**
  1. **Use an account from an allowed domain:** Add only users whose email is on a domain already allowed by the org (e.g. your school or org email).
  2. **Ask an org admin to allow a domain:** An organization policy administrator can add domains to the **Domain Restricted Sharing** policy so that principals from those domains (e.g. a partner domain) can be granted access. See [Domain restricted sharing](https://cloud.google.com/resource-manager/docs/organization-policy/restricting-domains).
  3. **Ask an org admin to grant access for you:** If you need to give a specific person access and their domain cannot be added, an admin may be able to add them via a group that is in an allowed domain, or by using a different mechanism (e.g. Identity Platform) that sits outside this IAM restriction.

You cannot disable or change this policy from within the project; it is set at the organization or folder level.

### Opening the Cloud Run URL in the browser shows "Access denied"

**Yes — opening the Cloud Run service URL in a browser is how you access the web application.** "Access denied" usually means the service is set to **Require authentication** but the Google account you’re signed in with does **not** have permission to invoke the service.

**Fix:**

1. **Use the same Google account you use for the GCP project** when you open the URL (or the account you intend to grant access to).
2. **Grant that account access** to the service:
   - **If using IAP:** Cloud Run → your service → **Security** → under IAP, **Edit policy** → add your principal (e.g. `user:you@yourdomain.com`) and save.
   - **If using Cloud Run Invoker (no IAP):** Use the **Permissions** panel (checkbox next to the service → right-hand panel → **Permissions** → **Grant access**) and add your email with role **Cloud Run Invoker**. Or run:
     ```bash
     gcloud run services add-iam-policy-binding SERVICE_NAME --region=REGION --member="user:YOUR_EMAIL" --role="roles/run.invoker"
     ```
     Example: `gcloud run services add-iam-policy-binding audio-pipeline --region=us-central1 --member="user:you@example.com" --role="roles/run.invoker"`.
3. **Reload the Cloud Run URL** in the browser (or open it in an incognito window and sign in with that account). You should be prompted to sign in with Google if needed, then the app should load.

**Note:** Being a project Owner or Editor does **not** automatically grant invoke permission on the service. You must add yourself (or the group you’re in) as a principal with **Cloud Run Invoker** or IAP access for that service.

### "Error: Forbidden - Your client does not have permission to get URL / from this server" (even after adding Cloud Run Invoker)

This message comes from Cloud Run’s auth layer. The most common cause is **IAP is still enabled**. When IAP is on, **IAP runs first** and decides who can reach the service; Cloud Run Invoker is only used by the IAP proxy to call your service. So if you added only **Cloud Run Invoker** and did not add the same users to the **IAP policy**, IAP will block the request and you get this Forbidden.

**Fix:**

1. **Disable IAP and use only Cloud Run Invoker** (recommended if you need personal Gmail or mixed accounts):
   - Cloud Run → your service → **Security** tab.
   - Under **Authentication**, change to **Require authentication** but **do not** use Identity-Aware Proxy (IAP). If you see an option like “Allow unauthenticated invocations” vs “Require authentication,” choose “Require authentication” and ensure IAP is **off** (e.g. “Use IAP” unchecked, or use the option that does not mention IAP).
   - Save. Wait a minute, then open the service URL again in the browser. You should be prompted to **sign in with Google**; use an account that has **Cloud Run Invoker** on this service. The app should then load.

2. **If you must keep IAP:** Add each allowed user in the **IAP** policy (Security → IAP → Edit policy), not only as Invoker. Only accounts from your **same organization** can be added to IAP. Personal Gmail cannot be added to IAP.

3. **Ensure the browser is sending your identity:** Open the Cloud Run URL in a normal browser window (or incognito). When prompted, sign in with the exact Google account you granted Cloud Run Invoker to. If you’re not prompted to sign in, try incognito/private or another browser and sign in when asked.

4. **Confirm principals:** In the **Permissions** panel (checkbox next to service → right panel → Permissions), verify the principal is exactly `user:your@gmail.com` (or your org email) with role **Cloud Run Invoker**. Fix any typo or wrong email.

After disabling IAP and using only Invoker, the “permission to get URL” error should stop for accounts that have Invoker.

### Build failed: `build.service_account` / `logs_bucket` (invalid argument)

If the trigger fails with: *"if 'build.service_account' is specified, the build must either (a) specify 'build.logs_bucket', (b) use the REGIONAL_USER_OWNED_BUCKET ... or (c) use either CLOUD_LOGGING_ONLY / NONE logging options"*:

- **Option A (Console):** Edit the trigger → **Advanced** → set **Logging** to **Cloud Logging only** (or **None**). Then save and re-run.
- **Option B (use repo config):** In the trigger, set **Configuration** to **Build configuration file**, set the path to `cloudbuild.yaml`. The repo `cloudbuild.yaml` includes `options.logging: CLOUD_LOGGING_ONLY`, so the build satisfies the requirement even when a custom service account is used.

### Build failed: service account does not have permission to write logs

If the build fails with *"The service account ... does not have permission to write logs to Cloud Logging"* (e.g. when using `github-deploy@...` with **Cloud Logging only**):

Grant the **Logs Writer** role to the service account used by the trigger:

```bash
gcloud projects add-iam-policy-binding ask-the-elect \
  --member="serviceAccount:github-deploy@ask-the-elect.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

Replace the service account email with the one shown in the error if different. Then re-run the trigger.

### Build failed: Permission `artifactregistry.repositories.uploadArtifacts` denied

If the build fails at the **docker push** step with *"Permission 'artifactregistry.repositories.uploadArtifacts' denied on resource (or it may not exist)"*:

The service account used by the trigger needs **Artifact Registry Writer** so it can push the image. Grant it (use the same service account as in your trigger, e.g. `github-deploy@...`):

```bash
gcloud projects add-iam-policy-binding ask-the-elect \
  --member="serviceAccount:github-deploy@ask-the-elect.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

Ensure the Artifact Registry repo exists: `gcloud artifacts repositories create audio-pipeline --repository-format=docker --location=us-central1` (ignore if it already exists). Then re-run the trigger.

### Container failed to start and listen on PORT

If a revision fails with *"The user-provided container failed to start and listen on the port defined by PORT=8080 within the allocated timeout"*:

- The app defers DB/ffmpeg/queue init to a background thread so the server binds to `PORT` immediately. Redeploy with the latest code. (The container image includes ffmpeg; for local runs without system ffmpeg, `requirements.txt` includes static-ffmpeg so the app can use bundled ffmpeg/ffprobe with no admin.)
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
