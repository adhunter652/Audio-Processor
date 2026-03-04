import 'package:dio/dio.dart';

import '../config/app_config.dart';

/// Creates and configures the app Dio instance.
class DioClientFactory {
  /// Create Dio with optional initial [idToken].
  Dio create({String? idToken}) {
    final dio = Dio(BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 15),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (idToken != null && idToken.isNotEmpty) 'Authorization': 'Bearer $idToken',
      },
    ));
    return dio;
  }

  /// Create Dio with a getter that supplies the current ID token per request (e.g. from Firebase).
  Dio createWithTokenGetter(Future<String?> Function() getToken) {
    final dio = Dio(BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 15),
      headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
    ));
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await getToken();
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
    ));
    return dio;
  }
}
