import 'package:dio/dio.dart';
import 'package:provider/provider.dart';
import 'package:provider/single_child_widget.dart';

import '../network/dio_client.dart';
import '../../features/auth/domain/repositories/auth_repository.dart';
import '../../features/auth/data/repositories/auth_repository_impl.dart';
import '../../features/search/domain/repositories/search_repository.dart';
import '../../features/search/data/data_sources/remote/search_api.dart';
import '../../features/search/data/mappers/search_mapper.dart';
import '../../features/search/data/repositories/search_repository_impl.dart';
import '../../features/search/presentation/state/providers/search_provider.dart';

List<SingleChildWidget> buildAppProviders() {
  return [
    Provider<AuthRepository>(
      create: (_) => AuthRepositoryImpl(),
    ),
    ProxyProvider<AuthRepository, Dio>(
      update: (_, auth, __) {
        final factory = DioClientFactory();
        return factory.createWithTokenGetter(() => auth.getIdToken());
      },
    ),
    ProxyProvider<Dio, SearchApi>(
      update: (_, dio, __) => DioSearchApi(dio),
    ),
    Provider<SearchMapper>(
      create: (_) => const SearchMapper(),
    ),
    Provider<SearchRepository>(
      create: (ctx) => SearchRepositoryImpl(
        api: ctx.read<SearchApi>(),
        mapper: ctx.read<SearchMapper>(),
      ),
    ),
    ChangeNotifierProxyProvider<SearchRepository, SearchProvider>(
      create: (ctx) => SearchProvider(ctx.read<SearchRepository>()),
      update: (_, repo, __) => SearchProvider(repo),
    ),
  ];
}
