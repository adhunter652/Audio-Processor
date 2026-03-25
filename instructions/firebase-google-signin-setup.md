# Firebase and Google Sign-In Setup for Mobile App

This document describes how to configure **Firebase** and **Google Sign-In** so the mobile app can authenticate users with their Google account.

---

## 1. Create a Firebase project

1. Go to [Firebase Console](https://console.firebase.google.com/).
2. Click **Add project** (or use an existing project).
3. Follow the steps (name, Analytics optional, Create project).

---

## 2. Register the app with Firebase

### Android

1. In the Firebase project, click the **Android** icon to add an Android app.
2. **Android package name**: use the value from `mobile/android/app/build.gradle.kts` (e.g. `com.example.mobile`).
3. **Required for Google Sign-In:** Add your **Debug signing certificate SHA-1** (and optionally SHA-256):
   - In Firebase: Project settings (gear) → Your apps → select the Android app → **Add fingerprint**.
   - Use the **Debug** SHA-1 from your machine (see [Troubleshooting: Error 10](#sign-in-error-10-apiexception-10) below), or run `cd mobile && .\gradlew.bat signingReport` (Windows) / `./gradlew signingReport` (macOS/Linux) and copy the SHA-1 from the `debug` variant.
4. Download **google-services.json** and place it at:
   - `mobile/android/app/google-services.json`
   - **Do not commit this file** — it is in `.gitignore`. Use `google-services.json.example` as a template if setting up on a new machine.
5. Finish the wizard.

### iOS

1. In the same Firebase project, click **Add app** → **iOS**.
2. **iOS bundle ID**: use the value from `mobile/ios/Runner/Info.plist` (e.g. `com.example.mobile`).
3. Download **GoogleService-Info.plist** and add it to the Xcode project:
   - Open `mobile/ios/Runner.xcworkspace` in Xcode.
   - Drag `GoogleService-Info.plist` into the **Runner** group and ensure “Copy items if needed” and the Runner target are selected.
4. Finish the wizard.

---

## 3. Enable Authentication and Google provider

1. In Firebase Console, go to **Build** → **Authentication**.
2. Click **Get started**.
3. Open the **Sign-in method** tab.
4. Click **Google** → **Enable** → set **Project support email** → **Save**.

---

## 4. Flutter Firebase configuration

1. Install the FlutterFire CLI (one-time):
   ```bash
   dart pub global activate flutterfire_cli
   ```
2. From the **mobile** directory, run:
   ```bash
   cd mobile
   flutterfire configure
   ```
   This will:
   - Create/select the Firebase project and apps (Android/iOS).
   - Generate `lib/firebase_options.dart` with API keys and config (do not commit secrets if you use a private repo; add `firebase_options.dart` to `.gitignore` if required).

---

## 5. Android: Google Sign-In

- The app uses **google_sign_in** and **firebase_auth**. No extra Android config is required if you added the debug SHA-1 in step 2.
- For release builds, add the **release** SHA-1 in the Firebase Console (Android app settings) and, if needed, in the [Google Cloud Console](https://console.cloud.google.com/) for the OAuth 2.0 client used by Google Sign-In.

---

## 6. iOS: Google Sign-In

- Ensure **GoogleService-Info.plist** is in the Runner target (step 2).
- The first time you run, you may need to open `mobile/ios/Runner.xcworkspace` in Xcode and run from Xcode so that CocoaPods and signing are set up correctly.

---

## 7. Run the app

1. Start the **web_server** backend (so the app can call the search API).
2. Set the backend URL if not using default:
   - Default is `http://localhost:8000`. For an Android emulator use `http://10.0.2.2:8000` (e.g. via `--dart-define=API_BASE_URL=http://10.0.2.2:8000`).
3. Run the Flutter app:
   ```bash
   cd mobile
   flutter run
   ```
4. Tap **Sign in with Google**, complete the flow, then use the search screen.

---

## 8. Troubleshooting

### Sign-in error 10 (ApiException: 10)

**Error:** `sign_in_failed`, `com.google.android.gms.common.api.ApiException: 10`  

This means the **SHA-1 fingerprint** of the keystore used to sign your app is **not registered** in Firebase. Google Sign-In will not work until you add it.

**Fix:**

1. Open [Firebase Console](https://console.firebase.google.com/) → your project → **Project settings** (gear icon).
2. Under **Your apps**, select the **Android** app (package name `com.mla.asktheelect`).
3. Click **Add fingerprint** and paste your certificate SHA-1.
4. (Optional) Add the **SHA-256** fingerprint as well.
5. **Re-download** `google-services.json`: same page → **Download google-services.json**. Replace `mobile/android/app/google-services.json` with it (the new file will include `oauth_client` entries; without this, Sign-In can still fail with error 10).
6. Save and wait 1–2 minutes, then do a **clean run**: `flutter clean && flutter pub get && flutter run`. Try signing in again.

**Fingerprints:** Do not paste real SHA-1/SHA-256 values into this repo. For your machine, run from `mobile`:

- Debug: `.\get-sha1-debug.ps1` (or `.\gradlew.bat :app:signingReport` if Gradle works on your JDK).
- Release: use your release keystore script or `keytool -list -v` on the keystore you use for Play builds.

In Firebase → Project settings → Android app (`com.mla.asktheelect`) → **Add fingerprint**, add at least the **Debug** SHA-1 when using `flutter run` (emulator or physical device).

- **Debug** (e.g. `flutter run` on emulator or **physical device**): add the **Debug** SHA-1 (and optionally SHA-256). The app is signed with the debug keystore on the machine where you run `flutter run`.
- **Release**: add the **Release** SHA-1 when building for Play Store.

If you build on a **different machine**, that machine has its own debug keystore: run `cd mobile && .\gradlew.bat signingReport` there and add the **debug** SHA-1 shown for that machine to Firebase.

---

| Issue | What to check |
|-------|----------------|
| **Google Sign-In fails on Android (error 10)** | Add the **Debug** (and Release) SHA-1 in Firebase → Project settings → Android app → Add fingerprint. See above. |
| **Google Sign-In fails on Android (other)** | Correct package name `com.mla.asktheelect`? Google provider enabled in Authentication? |
| **Google Sign-In fails on iOS** | `GoogleService-Info.plist` in Runner target? Bundle ID matches Firebase? |
| **Network/API errors** | Backend running? For emulator, using `10.0.2.2:8000` (Android) or `localhost:8000` (iOS sim)? |
| **Missing firebase_options.dart** | Run `flutterfire configure` from the `mobile` directory. |

---

## Rotating the Firebase/Google API key (if exposed)

If **google-services.json** (or its API key) was committed to a public repo:

1. **Create a new API key**
   - Open [Google Cloud Console](https://console.cloud.google.com/) and select your Firebase project (e.g. `ask-the-elect-bfa69`).
   - Go to **APIs & Services** → **Credentials**.
   - Click **+ CREATE CREDENTIALS** → **API key**. Copy the new key.
   - (Optional but recommended) Restrict the key: **Application restrictions** → **Android apps**, add your package name and SHA-1.
   - The new key is linked to the project in a few minutes.

2. **Use the new key in your app**
   - In [Firebase Console](https://console.firebase.google.com/) → Project **Settings** (gear) → **Your apps** → Android app, re-download **google-services.json**.
   - If the downloaded file still has the old key, edit `mobile/android/app/google-services.json` and set `client[0].api_key[0].current_key` to the new API key from Cloud Console.
   - Then in Cloud Console → **Credentials**, delete the old (compromised) API key so it stops working.

3. **Stop tracking the secret file**
   - Run: `git rm --cached mobile/android/app/google-services.json` (keeps the file on disk, removes it from Git).
   - Commit the change. The file is in `.gitignore`, so it will not be re-added.
   - Consider using [BFG or git filter-repo](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) to remove the key from past commits if the repo is public and the key was truly sensitive.

4. **Prevention**
   - `google-services.json` and `GoogleService-Info.plist` are in `.gitignore`. Use `google-services.json.example` as a template; never commit the real file.

---

## Summary

- Create a Firebase project and add Android + iOS apps.
- Add **google-services.json** (Android) and **GoogleService-Info.plist** (iOS).
- Enable **Google** in Authentication → Sign-in method.
- Run `flutterfire configure` in `mobile` to generate `lib/firebase_options.dart`.
- Add debug (and release) SHA-1 for Android in Firebase and Google Cloud if needed.

After this, the app’s **Sign in with Google** flow will use Firebase Auth and the backend can later verify requests using the Firebase ID token if you add auth to the web_server.
