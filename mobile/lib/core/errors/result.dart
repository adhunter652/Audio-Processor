import 'failure.dart';

/// Result type: either success [T] or [Failure]. Used by repositories.
sealed class Result<T> {
  const Result();
}

final class Success<T> extends Result<T> {
  final T value;
  const Success(this.value);
}

final class Err<T> extends Result<T> {
  final Failure failure;
  const Err(this.failure);
}

extension ResultExtension<T> on Result<T> {
  bool get isSuccess => this is Success<T>;
  bool get isError => this is Err<T>;
  T? get valueOrNull => switch (this) {
        Success(:final value) => value,
        Err() => null,
      };
  Failure? get failureOrNull => switch (this) {
        Err(:final failure) => failure,
        Success() => null,
      };
}
