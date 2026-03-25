# Firebase Google Sign-In Setup (Android)

If you see **`ApiException: 10`** or **`sign_in_failed`** when tapping "Sign in with Google", the Android app is not yet authorized for Google Sign-In. Fix it by adding your **SHA-1 fingerprint** to Firebase and updating `google-services.json`.

## 1. Get your SHA-1 fingerprint

- **Debug builds** (running from IDE / `flutter run`):  
  From the `mobile` folder run:
  ```powershell
  .\get-sha1-debug.ps1
  ```
  Copy the printed SHA-1 (it’s also copied to the clipboard if possible).

- **Release builds**:  
  Use your release keystore with `get-sha1.ps1` (or the release script you use), then add that SHA-1 to Firebase as well.

## 2. Add SHA-1 in Firebase Console

1. Open [Firebase Console](https://console.firebase.google.com/).
2. Select project **ask-the-elect-bfa69**.
3. Go to **Project settings** (gear icon) → **Your apps**.
4. Under the Android app **com.mla.asktheelect**, click **Add fingerprint**.
5. Paste the SHA-1 from step 1 and save.

## 3. Download updated google-services.json

After adding the fingerprint, Firebase creates an OAuth client. You must use the updated config file:

1. In the same **Project settings → Your apps** page, find the Android app.
2. Click **Download google-services.json**.
3. Replace `mobile/android/app/google-services.json` with the downloaded file.

Your current file has `"oauth_client": []`. After adding SHA-1 and re-downloading, `oauth_client` will contain the OAuth client entries required for Google Sign-In.

---

## You need BOTH clients (Android + Web)

Your `oauth_client` must include an **Android** client (client_type: 1); without it you get **ApiException: 10**. It can also have the Web client (client_type: 3) for Firebase. If you only have the Web client, add the Android client as below.

---

## If `oauth_client` is still empty (or missing Android client) after adding SHA-1

Firebase sometimes doesn’t add the Android OAuth client to the downloaded file. Create it in **Google Cloud Console** and add it to `google-services.json` yourself.

### A. Create the Android OAuth client in Google Cloud

1. Open [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials) and select project **ask-the-elect-bfa69** (same as your Firebase project).
2. Click **+ Create credentials** → **OAuth client ID**.
3. If asked, set **Application type** to **Android**.
4. Fill in:
   - **Name:** e.g. `Android client (Ask the Elect)`
   - **Package name:** `com.mla.asktheelect`
   - **SHA-1 certificate fingerprint:** paste the value from `.\get-sha1-debug.ps1` (debug) or your release SHA-1.
5. Click **Create**. Copy the **Client ID**. It **must** start with your Firebase project number **802244164633** (e.g. `802244164633-xxxxxxxxxx.apps.googleusercontent.com`). If you see a different number (e.g. 158822246647), you created the client in the wrong GCP project — switch to project **ask-the-elect-bfa69** and create the Android client there.

### B. Add the Android client to google-services.json

1. Open `mobile/android/app/google-services.json`.
2. In the `oauth_client` array you must have an entry with **client_type: 1** (Android). If you only have the Web client (client_type: 3), **add** this object (use your Android Client ID from step A.5):

```json
        {
          "client_id": "802244164633-YOUR_ANDROID_SUFFIX.apps.googleusercontent.com",
          "client_type": 1
        }
```

Example: if `oauth_client` currently has only the Web client, make it:

```json
      "oauth_client": [
        {
          "client_id": "802244164633-YOUR_ANDROID_CLIENT_ID.apps.googleusercontent.com",
          "client_type": 1
        },
        {
          "client_id": "802244164633-YOUR_WEB_CLIENT_SUFFIX.apps.googleusercontent.com",
          "client_type": 3
        }
      ],
```

3. Save the file. `client_type`: 1 = Android, 3 = Web.

### C. Rebuild

```bash
cd mobile
flutter clean
flutter pub get
flutter run
```

---

## 4. Rebuild the app

```bash
cd mobile
flutter clean
flutter pub get
flutter run
```

Then try "Sign in with Google" again. If you use a different machine or a new debug keystore, repeat steps 1–4 with the new debug SHA-1.

---

## "access_token audience is not for this project"

Firebase Auth expects the Google ID token to be issued for your project’s **Web** OAuth client, not the Android client. You need to create a **Web application** OAuth client in the same project and pass its Client ID to the app.

### 1. Create the Web OAuth client (same project)

1. Open [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials) and select project **ask-the-elect-bfa69**.
2. Click **+ Create credentials** → **OAuth client ID**.
3. **Application type:** **Web application**.
4. **Name:** e.g. `Web client (Ask the Elect)`.
5. Under **Authorized redirect URIs** you can leave default or add any your backend needs. For Flutter + Firebase Auth you don’t need a redirect URI for this flow.
6. Click **Create**. Copy the **Client ID** (e.g. `802244164633-yyyyy.apps.googleusercontent.com`).

### 2. Link the Web client in Firebase (required)

1. Open [Firebase Console](https://console.firebase.google.com/) → project **ask-the-elect-bfa69**.
2. Go to **Authentication** → **Sign-in method**.
3. Click **Google** and ensure it is **Enabled**.
4. Under **Web SDK configuration**, set **Web client ID** and **Web client secret** to the values from the Web OAuth client you created in step 1 (same project). If Firebase already shows a default Web client, you can use that client’s ID as `GOOGLE_SIGN_IN_WEB_CLIENT_ID` instead of creating a new one.
5. Save.

If this isn’t set, sign-in can fail with errors that mention your project number.

### 3. Pass the Web Client ID to the app

The app reads it from the `GOOGLE_SIGN_IN_WEB_CLIENT_ID` compile-time variable. Run with:

```bash
cd mobile
flutter run --dart-define=GOOGLE_SIGN_IN_WEB_CLIENT_ID=802244164633-YYYYY.apps.googleusercontent.com
```

Replace `802244164633-YYYYY.apps.googleusercontent.com` with the Web client ID you copied. You can also set it in your IDE run configuration (e.g. **Additional run args**: `--dart-define=GOOGLE_SIGN_IN_WEB_CLIENT_ID=your_web_client_id`).

### 4. Optional: add Web client to google-services.json

You can add the same Web client to `oauth_client` in `google-services.json` as a second entry (e.g. `"client_type": 3` for Web). The app still needs the value at runtime via `--dart-define` (or similar) as above.
