# Feature Implementation

_Last updated: 2025-12-26_

This document defines how to implement features, including repository patterns, mappers, providers, and data flow.

---

## Feature splitting guidance (posts, feed, comments, replies)

Do **not** split "hive posting / business posting / event posting" into separate features.  
Instead:

-   Keep **one** `post` feature with a **context** object describing where the post belongs.
-   Keep **discussion** (comments/replies/threading) as a separate capability feature (or tightly coupled to `post` if you prefer).
-   Keep container pages (hive/business/event) in their own features and **compose** post/discussion widgets.

### Example: `PostContext` (avoid duplicated "BusinessPost/HivePost/EventPost" systems)

Put a stable shared context type in one place:

-   Option A: `features/post/domain/value_objects/post_context.dart`
-   Option B: `core/refs/post_context.dart` (if many features rely on it)

Example:

```dart
sealed class PostContext {
  const PostContext();
  String get type;
  String get id;
}

class HivePostContext extends PostContext {
  @override final String type = 'hive';
  @override final String id;
  const HivePostContext(this.id);
}

class BusinessPostContext extends PostContext {
  @override final String type = 'business';
  @override final String id;
  const BusinessPostContext(this.id);
}

class EventPostContext extends PostContext {
  @override final String type = 'event';
  @override final String id;
  const EventPostContext(this.id);
}
```

Now the same post screens/widgets can be reused by passing the context.

---

## Repository pattern (interfaces vs implementations)

### What is a repository?

A repository is the boundary between:

-   **Domain** (what the app means: entities, usecases)
-   **Data** (how the app fetches/stores: API/DB/cache/socket)

### Where do they live?

-   `features/<feature>/domain/repositories/*` → **interfaces (contracts)**
-   `features/<feature>/data/repositories/*` → **implementations**

### Repository interface rules (domain)

-   Returns **domain entities** (or `Result<T>` of entities)
-   Does not reference:
    -   DTOs
    -   Dio / HTTP
    -   DB APIs
    -   Flutter UI types
-   Stable API surface for presentation/state layers

#### Example: domain entity

`features/post/domain/entities/post.dart`

```dart
class Post {
  final String id;
  final String authorId;
  final String text;
  final DateTime createdAt;
  final List<PostMedia> media;

  const Post({
    required this.id,
    required this.authorId,
    required this.text,
    required this.createdAt,
    required this.media,
  });
}

class PostMedia {
  final String url;
  final String type;
  const PostMedia({required this.url, required this.type});
}
```

#### Example: repository interface

`features/post/domain/repositories/post_repository.dart`

```dart
import '../entities/post.dart';
import '../value_objects/post_context.dart';

abstract class PostRepository {
  Future<Post> getPost(String postId);

  Future<List<Post>> getFeed({
    required int page,
    required int perPage,
  });

  Future<List<Post>> getPostsForContext({
    required PostContext context,
    required int page,
    required int perPage,
  });

  Future<Post> createPost({
    required PostContext context,
    required String text,
    required List<String> mediaIds,
  });

  Stream<Post> watchPost(String postId);
}
```

### Repository implementation rules (data)

The implementation orchestrates:

-   remote datasource (API)
-   local datasource (cache/db)
-   mappers (DTO→Entity, LocalModel→Entity)
-   offline/caching strategy (cache-first, stale-while-revalidate, etc.)
-   error translation (to `Failure`/`AppException`)

#### Example: DTO (remote/API shape)

`features/post/data/models/post_dto.dart`

```dart
class PostDto {
  final String id;
  final String authorId;
  final String body;
  final String createdAtIso;
  final List<PostMediaDto> media;

  PostDto({
    required this.id,
    required this.authorId,
    required this.body,
    required this.createdAtIso,
    required this.media,
  });

  factory PostDto.fromJson(Map<String, dynamic> json) {
    return PostDto(
      id: json['id'] as String,
      authorId: json['author_id'] as String,
      body: json['body'] as String? ?? '',
      createdAtIso: json['created_at'] as String,
      media: (json['media'] as List<dynamic>? ?? [])
          .map((e) => PostMediaDto.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class PostMediaDto {
  final String url;
  final String type;
  PostMediaDto({required this.url, required this.type});

  factory PostMediaDto.fromJson(Map<String, dynamic> json) {
    return PostMediaDto(
      url: json['url'] as String,
      type: json['type'] as String,
    );
  }
}
```

#### Example: mapper (DTO → Entity)

`features/post/data/mappers/post_mapper.dart`

```dart
import '../../domain/entities/post.dart';
import '../models/post_dto.dart';

class PostMapper {
  const PostMapper();

  Post fromDto(PostDto dto) {
    return Post(
      id: dto.id,
      authorId: dto.authorId,
      text: dto.body,
      createdAt: DateTime.parse(dto.createdAtIso),
      media: dto.media.map((m) => PostMedia(url: m.url, type: m.type)).toList(),
    );
  }
}
```

#### Example: remote datasource interface + Dio implementation

`features/post/data/data_sources/remote/post_api.dart`

```dart
import '../../models/post_dto.dart';
import '../../../domain/value_objects/post_context.dart';

abstract class PostApi {
  Future<PostDto> fetchPost(String id);
  Future<List<PostDto>> fetchFeed({required int page, required int perPage});
  Future<List<PostDto>> fetchForContext({
    required PostContext context,
    required int page,
    required int perPage,
  });
  Future<PostDto> createPost({
    required PostContext context,
    required String text,
    required List<String> mediaIds,
  });
  Stream<PostDto> watchPost(String postId);
}
```

#### Example: local datasource interface

`features/post/data/data_sources/local/post_cache.dart`

```dart
abstract class PostCache {
  Future<String?> getRawJson(String postId);
  Future<void> putRawJson(String postId, String json);
}
```

#### Example: repository implementation

`features/post/data/repositories/post_repository_impl.dart`

```dart
import '../../domain/entities/post.dart';
import '../../domain/repositories/post_repository.dart';
import '../../domain/value_objects/post_context.dart';
import '../data_sources/local/post_cache.dart';
import '../data_sources/remote/post_api.dart';
import '../mappers/post_mapper.dart';
import '../models/post_dto.dart';

class PostRepositoryImpl implements PostRepository {
  final PostApi _api;
  final PostCache _cache;
  final PostMapper _mapper;

  PostRepositoryImpl({
    required PostApi api,
    required PostCache cache,
    required PostMapper mapper,
  }) : _api = api, _cache = cache, _mapper = mapper;

  @override
  Future<Post> getPost(String postId) async {
    final cachedJson = await _cache.getRawJson(postId);
    if (cachedJson != null) {
      final dto = PostDto.fromJson(_decodeJson(cachedJson));
      return _mapper.fromDto(dto);
    }

    final dto = await _api.fetchPost(postId);
    await _cache.putRawJson(postId, _encodeJson(_dtoToJson(dto)));
    return _mapper.fromDto(dto);
  }

  @override
  Future<List<Post>> getFeed({required int page, required int perPage}) async {
    final dtos = await _api.fetchFeed(page: page, perPage: perPage);
    return dtos.map(_mapper.fromDto).toList();
  }

  @override
  Future<List<Post>> getPostsForContext({
    required PostContext context,
    required int page,
    required int perPage,
  }) async {
    final dtos = await _api.fetchForContext(context: context, page: page, perPage: perPage);
    return dtos.map(_mapper.fromDto).toList();
  }

  @override
  Future<Post> createPost({
    required PostContext context,
    required String text,
    required List<String> mediaIds,
  }) async {
    final dto = await _api.createPost(context: context, text: text, mediaIds: mediaIds);
    return _mapper.fromDto(dto);
  }

  @override
  Stream<Post> watchPost(String postId) {
    return _api.watchPost(postId).map(_mapper.fromDto);
  }

  Map<String, dynamic> _decodeJson(String s) => throw UnimplementedError();
  String _encodeJson(Map<String, dynamic> map) => throw UnimplementedError();
  Map<String, dynamic> _dtoToJson(PostDto dto) => throw UnimplementedError();
}
```

---

## Mappers and object shape rules

### Three shapes (and where they live)

1. **Domain Entity** (canonical app object)

-   Location: `features/<feature>/domain/entities/`
-   Used by: UI, state, usecases
-   Rules: no JSON annotations, no Dio/DB imports, stable and convenient

2. **DTO / Remote Model** (API shape)

-   Location: `features/<feature>/data/models/`
-   Used by: remote datasource, mapper
-   Rules: mirrors backend JSON keys, `fromJson/toJson`

3. **Local Cache Model** (DB/cache shape)

-   Location: `features/<feature>/data/models/` or `data/data_sources/local/`
-   Used by: local datasource, mapper
-   Rules: fits local storage strategy (normalized columns or raw JSON)

### Mapper rules

-   Location: `features/<feature>/data/mappers/`
-   Mappers are the ONLY code that imports both DTO and Entity.
-   Entity must never import DTO.
-   UI must never import DTO.

---

## Provider usage rules (state management)

### Provider responsibilities

Provider is used for:

1. **Dependency injection (DI)**: providing repositories/services
2. **Simple UI state**: view-model style ChangeNotifiers for screens (forms, paging, selection)

Provider must NOT contain:

-   Dio calls
-   DB queries
-   DTO parsing/mapping
-   complicated caching/merge/retry logic

That logic belongs in repositories/usecases (data/domain).

### Provider placement

-   App-wide DI providers: `core/di/*`
-   Feature UI state providers: `features/<feature>/presentation/state/providers/*`

### Example: Feature UI provider (feed pagination)

`features/post/presentation/state/providers/post_feed_provider.dart`

```dart
import 'package:flutter/foundation.dart';
import '../../../domain/entities/post.dart';
import '../../../domain/repositories/post_repository.dart';

class PostFeedProvider extends ChangeNotifier {
  final PostRepository _repo;
  PostFeedProvider(this._repo);

  final List<Post> _items = [];
  List<Post> get items => List.unmodifiable(_items);

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  String? _error;
  String? get error => _error;

  int _page = 1;
  final int _perPage = 20;
  bool _hasMore = true;
  bool get hasMore => _hasMore;

  Future<void> loadInitial() async {
    _page = 1;
    _hasMore = true;
    _items.clear();
    await _loadPage();
  }

  Future<void> loadMore() async {
    if (_isLoading || !_hasMore) return;
    _page++;
    await _loadPage();
  }

  Future<void> _loadPage() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final posts = await _repo.getFeed(page: _page, perPage: _perPage);
      _items.addAll(posts);
      if (posts.length < _perPage) _hasMore = false;
    } catch (_) {
      _error = 'Failed to load feed';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
```

### Provider mounting (where to create them)

-   Prefer **screen-scoped providers** unless you need persistence across tabs/routes.
-   Provide at tab root when you want state to survive tab switches (e.g., main screen tabs).

---

## Flows (end-to-end)

### Typical read flow (UI → Provider → Usecase/Repository → API/Cache → Mapper → Entity → UI)

**Simple flow (direct repository):**

1. Screen triggers provider action: `loadInitial()`
2. Provider calls repository interface: `repo.getFeed(page, perPage)`
3. Repository implementation:
    - calls remote datasource (or cache first)
    - gets DTO(s)
    - maps DTO → Entity via mapper
    - returns Entity(s) to provider
4. Provider updates UI state and notifies listeners

**Complex flow (with usecase):**

1. Screen triggers provider action: `loadInitial()`
2. Provider calls usecase: `feedUsecase.execute(userId, page, perPage)`
3. Usecase applies business rules and calls repository: `repo.getFeed(...)`
4. Repository implementation:
    - calls remote datasource (or cache first)
    - gets DTO(s)
    - maps DTO → Entity via mapper
    - returns Entity(s) to usecase
5. Usecase applies additional business logic (filtering, sorting) and returns to provider
6. Provider updates UI state and notifies listeners

### Typical create flow (UI → Provider → Usecase → Repository → API → Mapper → Entity)

1. User submits form
2. Provider calls usecase: `createPostUsecase.execute(context, text, mediaIds)`
3. Usecase validates business rules (text length, media limits, etc.)
4. Usecase calls repository: `repo.createPost(context, text, mediaIds)`
5. Repository calls API, receives DTO, maps to Entity, returns Entity
6. Usecase returns Entity to provider
7. Provider inserts/updates list state

---

## Naming conventions

-   `*Repository` = domain contract
-   `*RepositoryImpl` = data implementation
-   `*Usecase` = domain business logic (orchestrates repositories)
-   `*Api` or `*RemoteDataSource` = network layer
-   `*Cache` or `*LocalDataSource` = local persistence layer
-   `*Dto` = API models
-   `*Mapper` = conversions between layers
-   `*Provider` = UI state

---

## Related Documentation

-   [usecases.md](./usecases.md) - When to use usecases vs repositories
-   [dependency_rules.md](./dependency_rules.md) - How layers depend on each other
-   [file_structure.md](./file_structure.md) - Feature folder structure
