Engineering Brief: Secure, Low-Cost Serverless Web App
Project Goal: Deploy a Python web application that is highly secure, handles large media uploads efficiently, and is strictly optimized to stay within Google Cloud Platform's (GCP) "Always Free" tier limits.

Phase 1: Compute & Deployment (Cloud Run)
The application will be hosted on Google Cloud Run to leverage serverless scale-to-zero capabilities.

Containerize the App: Ensure the Python app (Flask, FastAPI, Django, etc.) is containerized using a Dockerfile and listens on the port defined by the $PORT environment variable.

Deploy to Free Tier Region: Deploy the service to us-central1, us-east1, or us-west1 to qualify for the free tier.

Implement Cost Guardrails: During deployment, strictly limit the maximum instances to prevent runaway costs from sudden traffic spikes.

CLI Flag: --max-instances=5 (or your preferred low limit).

Phase 2: Media Uploads (Cloud Storage + Signed URLs)
To prevent large uploads from consuming Cloud Run memory or timing out the serverless instance, all media must bypass the compute layer and go directly to storage.

Provision Storage: Create a Google Cloud Storage (GCS) bucket in the same free-tier region as your Cloud Run service using the "Standard" storage class.

Configure CORS: Set a Cross-Origin Resource Sharing (CORS) policy on the GCS bucket to allow HTTP PUT requests from your Cloud Run app's domain.

Implement Signed URLs in Python: * Use the google-cloud-storage Python client library.

Create an API endpoint in the Python app that generates a V4 Signed URL for writing (PUT).

When a user wants to upload a file, the frontend JavaScript must first hit this Python endpoint to get the temporary Signed URL, and then upload the file directly to GCS using that URL.

Phase 3: Access Control (Identity-Aware Proxy)
Do not build a custom authentication flow. We will use GCP's Identity-Aware Proxy (IAP) native Cloud Run integration to act as a zero-trust gateway.

Enable Native IAP: In the Google Cloud Console, navigate to the Cloud Run service, select the Security tab, set it to Require authentication, and choose Identity-Aware Proxy (IAP).

Configure OAuth: You will be prompted to configure an OAuth Consent screen. Set it to "Internal" or "External" depending on your Google Workspace setup, and provide an app name.

Assign Roles: In the IAP settings panel, add the specific Google/Gmail addresses that are allowed to access the app. Assign them the role of IAP-Secured Web App User.

Note: Anyone attempting to visit the Cloud Run URL who is not on this list will be blocked by Google before their request ever reaches the Python app.

Phase 4: Billing & Alerts
Set Budget Alerts: Go to Billing > Budgets & alerts in the GCP Console.

Configure Thresholds: Create a budget capped at $5.00 and set it to send an email alert when actual or forecasted costs reach 50%, 90%, and 100% of that budget.

Phase 5: Batch Media Processing via GCP Spot Instances
Project Goal: Provision a high-compute Spot instance to process large media files via a Python pipeline, ensuring the system can gracefully handle sudden preemption (termination) by GCP.

Architecture & Rules of Engagement
To successfully use Spot instances for batch processing, you must strictly adhere to the following pattern:

No Local State: The Spot VM's local disk should only be used as a temporary scratchpad. It could vanish at any moment.

Decoupled Storage: Your Python script must pull an unprocessed media file from a Google Cloud Storage (GCS) "Input" bucket, process it, and immediately upload the result to an "Output" bucket.

Idempotency: If the VM is killed halfway through processing a video, the system must be able to spin up a new VM, grab that exact same video, and start over without corrupting your data.

This stage is the most critical and looks like this:
On the processing page, when the pipeline is run, a spot instance is spun up and starts processing the queue, results are stored in google cloud storage and a google cloud sql database.
