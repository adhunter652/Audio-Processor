/// Base exception for app-level errors. Use for throwing from data layer.
class AppException implements Exception {
  final String message;
  final Object? cause;

  const AppException(this.message, {this.cause});

  @override
  String toString() => 'AppException: $message${cause != null ? ' ($cause)' : ''}';
}
