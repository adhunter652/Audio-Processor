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
3. (Optional) App nickname and Debug signing SHA-1 — add a debug SHA-1 for local testing:
   - Run: `cd mobile && ./gradlew signingReport` (or on Windows: `gradlew.bat signingReport`).
   - Copy the SHA-1 from the `debug` variant and add it in the Firebase console.
4. Download **google-services.json** and place it at:
   - `mobile/android/app/google-services.json`
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

| Issue | What to check |
|-------|----------------|
| **Google Sign-In fails on Android** | Debug SHA-1 added in Firebase (and Google Cloud OAuth client)? Correct package name? |
| **Google Sign-In fails on iOS** | `GoogleService-Info.plist` in Runner target? Bundle ID matches Firebase? |
| **Network/API errors** | Backend running? For emulator, using `10.0.2.2:8000` (Android) or `localhost:8000` (iOS sim)? |
| **Missing firebase_options.dart** | Run `flutterfire configure` from the `mobile` directory. |

---

## Summary

- Create a Firebase project and add Android + iOS apps.
- Add **google-services.json** (Android) and **GoogleService-Info.plist** (iOS).
- Enable **Google** in Authentication → Sign-in method.
- Run `flutterfire configure` in `mobile` to generate `lib/firebase_options.dart`.
- Add debug (and release) SHA-1 for Android in Firebase and Google Cloud if needed.

After this, the app’s **Sign in with Google** flow will use Firebase Auth and the backend can later verify requests using the Firebase ID token if you add auth to the web_server.
