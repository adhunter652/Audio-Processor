import '../entities/app_user.dart';

import '../../../../core/errors/result.dart';

/// Contract for authentication (Google Sign-in via Firebase).
abstract class AuthRepository {
  /// Current user if signed in; null otherwise.
  AppUser? get currentUser;

  /// Stream of auth state (signed in / signed out).
  Stream<AppUser?> get authStateChanges;

  /// Get current Firebase ID token for API calls. Returns null if not signed in.
  Future<String?> getIdToken();

  /// Sign in with Google. Returns [Success] with user or [Err] with [Failure].
  Future<Result<AppUser>> signInWithGoogle();

  /// Sign out.
  Future<void> signOut();
}
