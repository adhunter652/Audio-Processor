/// Domain-level failure representation (no HTTP/Flutter types).
abstract class Failure {
  String get message;
}

class ServerFailure implements Failure {
  @override
  final String message;
  final int? statusCode;

  const ServerFailure(this.message, {this.statusCode});
}

class NetworkFailure implements Failure {
  @override
  final String message;

  const NetworkFailure([this.message = 'Network error']);
}

class AuthFailure implements Failure {
  @override
  final String message;

  const AuthFailure([this.message = 'Authentication failed']);
}

class UnknownFailure implements Failure {
  @override
  final String message;

  const UnknownFailure([this.message = 'Something went wrong']);
}
