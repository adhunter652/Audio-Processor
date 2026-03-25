/// App-wide configuration: API base URL and constants.
class AppConfig {
  AppConfig._();

  /// Base URL for the web_server backend. Override for emulator: use 10.0.2.2:8000 (Android) or localhost:8000 (iOS).
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const int searchLimit = 20;

  /// Web OAuth client ID for Google Sign-In (Firebase Auth). Required on Android so the ID token
  /// audience matches Firebase. Create a "Web application" OAuth client in the same GCP project
  /// as your Firebase app and set via --dart-define=GOOGLE_SIGN_IN_WEB_CLIENT_ID=xxx or here.
  static const String googleSignInWebClientId = String.fromEnvironment(
    'GOOGLE_SIGN_IN_WEB_CLIENT_ID',
    defaultValue: '',
  );
}
