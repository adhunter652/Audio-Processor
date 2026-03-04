import 'failure.dart';

/// Turns [Failure] or [Object] into a user-facing message for UI (e.g. SnackBar).
class ErrorHandler {
  ErrorHandler._();

  static String message(Object error) {
    if (error is Failure) {
      return error.message;
    }
    if (error is Exception) {
      final s = error.toString();
      if (s.startsWith('Exception: ')) return s.substring(11);
      return s;
    }
    return error.toString().replaceFirst(RegExp(r'^Exception:\s*'), '');
  }
}
