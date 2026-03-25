# Fix ApiException: 10 (DEVELOPER_ERROR) — Checklist

When you still get **10: null, null** with the correct Android client ID in `google-services.json`, the cause is almost always a **SHA-1 mismatch**: the app is signed with a key whose SHA-1 is **not** the one on your Android OAuth client in Google Cloud.

## 1. Get the SHA-1 that actually signs your app

From the `mobile` folder:

```powershell
.\get-sha1-debug.ps1
```

Copy the SHA-1 it prints (e.g. `A1:B2:C3:...`). This is from **this machine’s** debug keystore (`%USERPROFILE%\.android\debug.keystore`). If you built the app on another PC or with a different user, that machine has a **different** debug SHA-1.

**Optional** — confirm what Gradle uses for debug: run from `mobile/android`: `.\gradlew.bat :app:signingReport`. Under `Variant: debug`, use the SHA-1 shown. If that command fails (e.g. with Java 24 you may see “What went wrong: 25.0.1” due to a Kotlin/Gradle compatibility issue), skip it and rely on `get-sha1-debug.ps1`; that value is what matters for the OAuth client.

## 2. Make sure that SHA-1 is on your Android OAuth client

1. Open [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials).
2. Select project **ask-the-elect-bfa69**.
3. Find your **Android** OAuth 2.0 Client ID (the one listed in `google-services.json` under `oauth_client` with `"client_type": 1`).
4. Open it and check the **SHA-1 certificate fingerprint**.
5. It must **exactly** match the SHA-1 from step 1 (with or without colons — GCP usually accepts both).

If it does **not** match (e.g. you created the client on another machine or with a different key):

- Create a **new** Android OAuth client in the same project:
  - Application type: **Android**
  - Package name: `com.mla.asktheelect`
  - SHA-1: paste the value from step 1
- Copy the new Client ID (it will start with `802244164633-`).
- In `mobile/android/app/google-services.json`, in the `oauth_client` array, replace the **Android** entry (the one with `"client_type": 1`) with this new `client_id`.

## 3. Add the same SHA-1 in Firebase (optional but recommended)

1. [Firebase Console](https://console.firebase.google.com/) → project **ask-the-elect-bfa69** → **Project settings** → **Your apps**.
2. Select the Android app **com.mla.asktheelect**.
3. If the SHA-1 from step 1 is not listed, click **Add fingerprint** and add it.

## 4. Clean rebuild and reinstall

```bash
cd mobile
flutter clean
flutter pub get
flutter run --dart-define=GOOGLE_SIGN_IN_WEB_CLIENT_ID=YOUR_WEB_CLIENT_ID.apps.googleusercontent.com
```

Uninstall the app from the device/emulator before running if you’ve been changing signing or config, so the new build is installed with the correct signature.

---

**Summary:** ApiException 10 means “this app’s signing certificate doesn’t match the Android OAuth client.” The SHA-1 from `get-sha1-debug.ps1` (for the build you’re running) must be the one on that Android client in GCP (and ideally in Firebase too). If you switched machines or users, create a new Android client with the **current** SHA-1 and put its Client ID in `google-services.json`.

---

## Debug vs release: you need both SHA-1s

- **Debug builds** (`flutter run` / IDE) use the **debug** keystore → that SHA-1 must have an Android OAuth client.
- **Release builds** use the **release** keystore → that SHA-1 must also have an Android OAuth client.

If Sign-In works in release but not in debug (ApiException: 10 in debug), add a **second** Android OAuth client for the **debug** SHA-1 and add it to `google-services.json`.

### Steps

1. **Get your debug SHA-1** (from `mobile`): run `.\get-sha1-debug.ps1`. Use the value it prints (e.g. `AA:BB:CC:...`).

2. **Create a second Android OAuth client** in [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials), project **ask-the-elect-bfa69**: Create credentials → OAuth client ID → Android. Package name: `com.mla.asktheelect`. SHA-1: paste the **debug** SHA-1 from step 1. Create and copy the new **Client ID** (starts with `802244164633-`).

3. **Add it to `google-services.json`**  
   Replace the placeholder in the second Android entry: find `802244164633-PASTE_DEBUG_ANDROID_CLIENT_ID_HERE.apps.googleusercontent.com` and replace the **entire** `client_id` value with your new debug Client ID (e.g. `802244164633-xxxxxxxxxx.apps.googleusercontent.com`). You should have two Android entries (client_type 1) and one Web entry (client_type 3).

4. **Optional:** Firebase Console → Project settings → Your apps → Android app → Add fingerprint → add the debug SHA-1.

5. Rebuild and run in debug; Sign-In should work.
