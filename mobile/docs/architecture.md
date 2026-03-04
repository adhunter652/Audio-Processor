# HubHive Flutter App Architecture (Option A: `core/` + `features/`)

_Last updated: 2025-12-26_

This document defines the **target architecture** for the Flutter mobile app using a **feature-sliced** structure with a shared **core** layer (Option A).  
It is written to be **AI-friendly**: clear rules, dependency directions, folder conventions, and code examples so an AI can compare the current implementation against this target and suggest concrete changes.

---

## Goals

-   Keep code **modular**, **testable**, and **easy to evolve**.
-   Prevent a “overlord `app/` folder” where everything depends on everything.
-   Make ownership obvious: **feature code lives with the feature**, cross-cutting concerns live in **core**.
-   Enforce boundaries so refactors don’t cascade through the entire codebase.

---

## High-level structure

```
lib/
  core/                  # shared, cross-cutting plumbing used by many features
  features/              # vertical slices by capability/bounded context
  main.dart
  flavors/               # (optional) if you keep them here
  firebase/              # (optional) if you keep them here
```

### Core vs Feature rule

-   Put code in **`core/`** if it is:

    -   app plumbing (network, DI, routing)
    -   cross-cutting (analytics, permissions)
    -   stable shared primitives (Result/Failure, pagination types, IDs)
    -   reusable UI system components used everywhere

-   Put code in **`features/<feature>/`** if it is:
    -   owned by one domain/capability (post, hive, business, event, etc.)
    -   screens/widgets/state for that capability
    -   its API/cache/mappers/repositories

---

## Target `core/` layout

```
core/
  config/                # env, flavors, constants
  di/                    # Provider wiring (composition root)
  network/
    dio_client.dart
    interceptors/
  storage/
    local_database/       # db engine setup/adapters; feature-specific tables stay in features
    secure_storage/
  platform/
    method_channels/      # lowest-level platform channel wrappers
  navigation/             # app routing, observers, transitions (shared)
  permissions/
  analytics/
  session_recorder/
  realtime/               # socket base client (if truly app-wide)
  streams/                # global event bus only if truly global
  errors/
    app_exception.dart
    failure.dart
    result.dart
  utils/
    date/
    format/
    text/
  theme/
  shared_widgets/         # shared design system widgets (buttons, inputs, etc.)
```

---

## Target `features/<feature>/` layout

Every feature is a vertical slice:

```
features/<feature>/
  domain/
    entities/
    value_objects/         # IDs, context objects, small types (feature-owned)
    repositories/          # repository interfaces (contracts)
    usecases/              # optional but recommended for complex flows
  data/
    models/                # DTOs, DB models (NOT domain entities)
    data_sources/
      remote/              # API clients (Dio wrappers etc.)
      local/               # cache/db per feature
    mappers/               # DTO <-> Entity; LocalModel <-> Entity
    repositories/          # repository implementations
  presentation/
    screens/
    widgets/
    state/
      providers/
      blocs/
      cubits/
    validators/
    utils/                 # UI formatting helpers (not business rules)
```

---

## Dependency rules (must-follow)

### Layer dependency direction

-   `presentation` → depends on `domain` (and optionally `core`)
-   `data` → depends on `domain` (implements domain contracts)
-   `domain` → depends on **nothing** Flutter-specific (no `BuildContext`, no Dio, no DB)

### Cross-feature dependency direction

Use a **container vs capability** model:

-   **Container features** (pages/tabs/ownership): `hive`, `business`, `event`
-   **Capability features** (reusable engines): `post`, `discussion`, `media`, `search`, `notification`

Rules:

-   ✅ Container features may import capability features.
-   ❌ Capability features must NOT import container features.
-   Avoid cross-feature domain imports. If a shared concept is needed, move a small stable type into `core/`.

### Allowed imports

-   `features/business/presentation/*` can import `features/post/presentation/widgets/*` for composition.
-   `features/business/presentation/*` can depend on `features/post/domain/*` (interfaces/entities) via DI.
-   `features/post/data/*` can depend on `core/network`, `core/storage`, etc.

### Avoid

-   `features/post/*` importing `features/business/*`
-   `features/post/domain/*` importing any other feature domain
-   `features/business/data/*` importing `features/post/data/*`

---

## Feature splitting guidance (posts, feed, comments, replies)

Do **not** split “hive posting / business posting / event posting” into separate features.  
Instead:

-   Keep **one** `post` feature with a **context** object describing where the post belongs.
-   Keep **discussion** (comments/replies/threading) as a separate capability feature (or tightly coupled to `post` if you prefer).
-   Keep container pages (hive/business/event) in their own features and **compose** post/discussion widgets.

### Example: `PostContext` (avoid duplicated “BusinessPost/HivePost/EventPost” systems)

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

## Usecases (domain business logic)

### What is a usecase?

A usecase encapsulates a **single business operation** that orchestrates one or more repository calls and applies domain rules. Usecases live in the **domain layer** and are pure business logic—they don't know about HTTP, databases, or UI.

### When to use usecases vs repositories

**Use repositories directly** when:

-   The operation is a simple CRUD call (get, create, update, delete)
-   No business rules or validation are needed
-   No coordination between multiple repositories is required

**Create a usecase** when:

-   You need to coordinate multiple repository calls
-   Business rules or validation must be applied
-   The operation involves conditional logic or decision-making
-   You want to make the business intent explicit and testable
-   The flow is complex enough that it shouldn't live in a provider

### Usecase rules

-   Location: `features/<feature>/domain/usecases/`
-   Dependencies: Can depend on repository interfaces, entities, value objects, and other usecases within the same feature
-   Must NOT depend on: DTOs, data layer, presentation layer, or other features
-   Returns domain entities or `Result<T>` types
-   Pure business logic—no side effects beyond calling repositories

### Example: Simple usecase (post creation with validation)

`features/post/domain/usecases/create_post_usecase.dart`

```dart
import '../entities/post.dart';
import '../repositories/post_repository.dart';
import '../value_objects/post_context.dart';

class CreatePostUsecase {
  final PostRepository _postRepository;

  CreatePostUsecase(this._postRepository);

  Future<Post> execute({
    required PostContext context,
    required String text,
    required List<String> mediaIds,
  }) async {
    // Business rule: text must not be empty if no media
    if (text.trim().isEmpty && mediaIds.isEmpty) {
      throw ArgumentError('Post must have either text or media');
    }

    // Business rule: text length limit
    if (text.length > 5000) {
      throw ArgumentError('Post text cannot exceed 5000 characters');
    }

    // Business rule: media limit
    if (mediaIds.length > 10) {
      throw ArgumentError('Post cannot have more than 10 media items');
    }

    return await _postRepository.createPost(
      context: context,
      text: text.trim(),
      mediaIds: mediaIds,
    );
  }
}
```

### Example: Complex usecase (coordinating multiple repositories)

`features/post/domain/usecases/share_post_usecase.dart`

```dart
import '../entities/post.dart';
import '../repositories/post_repository.dart';
import '../../notification/domain/repositories/notification_repository.dart';
import '../../user/domain/repositories/user_repository.dart';

class SharePostUsecase {
  final PostRepository _postRepository;
  final NotificationRepository _notificationRepository;
  final UserRepository _userRepository;

  SharePostUsecase({
    required PostRepository postRepository,
    required NotificationRepository notificationRepository,
    required UserRepository userRepository,
  })  : _postRepository = postRepository,
        _notificationRepository = notificationRepository,
        _userRepository = userRepository;

  Future<void> execute({
    required String postId,
    required String targetUserId,
    required String currentUserId,
  }) async {
    // 1. Verify post exists
    final post = await _postRepository.getPost(postId);

    // 2. Verify target user exists
    final targetUser = await _userRepository.getUser(targetUserId);
    if (targetUser == null) {
      throw ArgumentError('Target user not found');
    }

    // 3. Business rule: cannot share to yourself
    if (targetUserId == currentUserId) {
      throw ArgumentError('Cannot share post to yourself');
    }

    // 4. Business rule: cannot share if you're not the author
    if (post.authorId != currentUserId) {
      throw ArgumentError('Only post author can share');
    }

    // 5. Create share record (via repository)
    await _postRepository.sharePost(
      postId: postId,
      targetUserId: targetUserId,
    );

    // 6. Send notification (coordinate with notification feature)
    await _notificationRepository.createNotification(
      userId: targetUserId,
      type: 'post_shared',
      data: {'postId': postId, 'sharedBy': currentUserId},
    );
  }
}
```

### Example: Usecase with conditional logic and retry

`features/post/domain/usecases/refresh_post_with_fallback_usecase.dart`

```dart
import '../entities/post.dart';
import '../repositories/post_repository.dart';

class RefreshPostWithFallbackUsecase {
  final PostRepository _postRepository;

  RefreshPostWithFallbackUsecase(this._postRepository);

  Future<Post> execute(String postId) async {
    try {
      // Try to get fresh data from network
      return await _postRepository.getPost(postId);
    } catch (e) {
      // Business rule: if network fails, check if we have cached data
      // This is a business decision about offline behavior
      try {
        // Repository should handle cache-first logic, but if it throws,
        // we might want to return stale data or handle differently
        return await _postRepository.getPost(postId);
      } catch (_) {
        // Re-throw with more context
        throw Exception('Failed to load post: $postId');
      }
    }
  }
}
```

### Example: Usecase for feed aggregation

`features/post/domain/usecases/get_personalized_feed_usecase.dart`

```dart
import '../entities/post.dart';
import '../repositories/post_repository.dart';
import '../../user/domain/repositories/user_repository.dart';

class GetPersonalizedFeedUsecase {
  final PostRepository _postRepository;
  final UserRepository _userRepository;

  GetPersonalizedFeedUsecase({
    required PostRepository postRepository,
    required UserRepository userRepository,
  })  : _postRepository = postRepository,
        _userRepository = userRepository;

  Future<List<Post>> execute({
    required String userId,
    required int page,
    required int perPage,
  }) async {
    // 1. Get user preferences
    final user = await _userRepository.getUser(userId);
    if (user == null) {
      throw ArgumentError('User not found');
    }

    // 2. Business rule: apply personalization filters
    final blockedUserIds = user.blockedUserIds;
    final followedUserIds = user.followedUserIds;

    // 3. Get feed from repository
    final allPosts = await _postRepository.getFeed(
      page: page,
      perPage: perPage * 2, // Fetch more to account for filtering
    );

    // 4. Apply business rules: filter blocked users, prioritize followed users
    final filtered = allPosts
        .where((post) => !blockedUserIds.contains(post.authorId))
        .toList();

    // 5. Sort: followed users first, then by date
    filtered.sort((a, b) {
      final aIsFollowed = followedUserIds.contains(a.authorId);
      final bIsFollowed = followedUserIds.contains(b.authorId);
      if (aIsFollowed != bIsFollowed) {
        return aIsFollowed ? -1 : 1;
      }
      return b.createdAt.compareTo(a.createdAt);
    });

    // 6. Return paginated result
    return filtered.take(perPage).toList();
  }
}
```

### Usecase in provider flow

Providers call usecases instead of repositories when business logic is needed:

`features/post/presentation/state/providers/post_feed_provider.dart` (updated)

```dart
import 'package:flutter/foundation.dart';
import '../../../domain/entities/post.dart';
import '../../../domain/usecases/get_personalized_feed_usecase.dart';

class PostFeedProvider extends ChangeNotifier {
  final GetPersonalizedFeedUsecase _feedUsecase;
  final String _userId;

  PostFeedProvider({
    required GetPersonalizedFeedUsecase feedUsecase,
    required String userId,
  })  : _feedUsecase = feedUsecase,
        _userId = userId;

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
      // Call usecase instead of repository directly
      final posts = await _feedUsecase.execute(
        userId: _userId,
        page: _page,
        perPage: _perPage,
      );
      _items.addAll(posts);
      if (posts.length < _perPage) _hasMore = false;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
```

### Usecase dependency injection

Wire usecases in the DI container:

`core/di/app_providers.dart` (updated excerpt)

```dart
import '../../features/post/domain/repositories/post_repository.dart';
import '../../features/post/domain/usecases/create_post_usecase.dart';
import '../../features/post/domain/usecases/get_personalized_feed_usecase.dart';
import '../../features/user/domain/repositories/user_repository.dart';

List<SingleChildWidget> buildAppProviders() {
  return [
    // ... existing providers ...

    // Usecases
    ProxyProvider<PostRepository, CreatePostUsecase>(
      update: (_, repo, __) => CreatePostUsecase(repo),
    ),
    ProxyProvider2<PostRepository, UserRepository, GetPersonalizedFeedUsecase>(
      update: (_, postRepo, userRepo, __) => GetPersonalizedFeedUsecase(
        postRepository: postRepo,
        userRepository: userRepo,
      ),
    ),
  ];
}
```

#### Benefits of ProxyProvider for usecases

**1. Automatic dependency resolution**

-   `ProxyProvider` automatically waits for dependencies (repositories) to be available
-   Ensures repositories are created before usecases
-   No manual ordering of provider creation needed

**2. Lazy creation**

-   Usecases are only created when first accessed
-   Reduces initial app startup time
-   Memory efficient

**3. Single source of truth**

-   All dependency wiring happens in one place (`core/di/`)
-   Easy to see the dependency graph
-   Easy to swap implementations (e.g., for testing)

**4. Type-safe access**

-   Usecases are available via `Provider.of<CreatePostUsecase>(context)`
-   Compile-time checking ensures dependencies exist
-   IDE autocomplete works perfectly

#### Example: Using a usecase in a screen

**Without ProxyProvider (manual wiring - not recommended):**

```dart
// ❌ Bad: Manual dependency creation in screen
class CreatePostScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    // Manual wiring - error-prone, hard to test
    final repo = Provider.of<PostRepository>(context);
    final usecase = CreatePostUsecase(repo); // Created every build!

    return PostForm(usecase: usecase);
  }
}
```

**With ProxyProvider (recommended):**

```dart
// ✅ Good: Usecase provided via DI
class CreatePostScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    // Usecase is already created and cached by Provider
    final usecase = Provider.of<CreatePostUsecase>(context);

    return PostForm(usecase: usecase);
  }
}
```

#### Example: Using usecase in a provider

`features/post/presentation/state/providers/create_post_provider.dart`

```dart
import 'package:flutter/foundation.dart';
import '../../../domain/entities/post.dart';
import '../../../domain/usecases/create_post_usecase.dart';
import '../../../domain/value_objects/post_context.dart';

class CreatePostProvider extends ChangeNotifier {
  final CreatePostUsecase _createPostUsecase;

  CreatePostProvider(this._createPostUsecase);

  bool _isSubmitting = false;
  bool get isSubmitting => _isSubmitting;

  String? _error;
  String? get error => _error;

  Post? _createdPost;
  Post? get createdPost => _createdPost;

  Future<void> submitPost({
    required PostContext context,
    required String text,
    required List<String> mediaIds,
  }) async {
    _isSubmitting = true;
    _error = null;
    _createdPost = null;
    notifyListeners();

    try {
      // Usecase handles all validation and business rules
      _createdPost = await _createPostUsecase.execute(
        context: context,
        text: text,
        mediaIds: mediaIds,
      );
    } catch (e) {
      _error = e.toString();
    } finally {
      _isSubmitting = false;
      notifyListeners();
    }
  }
}
```

**Wiring the provider (in screen or DI):**

```dart
// In your screen or DI setup
ProxyProvider<CreatePostUsecase, CreatePostProvider>(
  update: (_, usecase, __) => CreatePostProvider(usecase),
  child: CreatePostScreen(),
)
```

#### Example: Testing with mocked usecase

Because usecases are provided via DI, testing is straightforward:

```dart
// test/features/post/presentation/state/providers/create_post_provider_test.dart
void main() {
  test('should create post successfully', () async {
    // Create mock usecase
    final mockUsecase = MockCreatePostUsecase();
    when(mockUsecase.execute(
      context: any,
      text: any,
      mediaIds: any,
    )).thenAnswer((_) async => Post(...));

    // Create provider with mock
    final provider = CreatePostProvider(mockUsecase);

    // Test
    await provider.submitPost(
      context: HivePostContext('hive-123'),
      text: 'Test post',
      mediaIds: [],
    );

    expect(provider.createdPost, isNotNull);
    expect(provider.error, isNull);
  });
}
```

#### Alternative: Direct Provider (when usecase has no dependencies)

If a usecase has no dependencies, you can use a regular `Provider`:

```dart
// Simple usecase with no dependencies
class ValidatePostTextUsecase {
  bool execute(String text) {
    return text.trim().isNotEmpty && text.length <= 5000;
  }
}

// In DI:
Provider<ValidatePostTextUsecase>(
  create: (_) => ValidatePostTextUsecase(),
)
```

But if it depends on repositories, always use `ProxyProvider` to ensure proper dependency ordering.

### Usecase vs Repository: Decision guide

| Scenario                                | Use Repository | Use Usecase |
| --------------------------------------- | -------------- | ----------- |
| Simple CRUD (get post by ID)            | ✅             | ❌          |
| Create post with validation             | ❌             | ✅          |
| Coordinate multiple repositories        | ❌             | ✅          |
| Apply business rules/filters            | ❌             | ✅          |
| Simple pagination                       | ✅             | ❌          |
| Personalized feed with filtering        | ❌             | ✅          |
| Conditional logic based on domain state | ❌             | ✅          |

### Anti-patterns (avoid)

-   ❌ Usecases that import DTOs or data layer code
-   ❌ Usecases that perform HTTP calls directly
-   ❌ Usecases that depend on other features' data layers
-   ❌ Providers that contain business logic instead of calling usecases
-   ❌ Usecases that are just pass-throughs to repositories (use repository directly)

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

### Example: App DI wiring (composition root)

`core/di/app_providers.dart`

```dart
import 'package:provider/provider.dart';
import 'package:provider/single_child_widget.dart';

import '../network/dio_client.dart';
import '../../features/post/domain/repositories/post_repository.dart';
import '../../features/post/data/repositories/post_repository_impl.dart';
import '../../features/post/data/data_sources/remote/post_api.dart';
import '../../features/post/data/data_sources/local/post_cache.dart';
import '../../features/post/data/mappers/post_mapper.dart';

List<SingleChildWidget> buildAppProviders() {
  return [
    Provider(create: (_) => DioClientFactory().create()),

    Provider<PostApi>(create: (ctx) => DioPostApi(ctx.read())),
    Provider<PostCache>(create: (_) => InMemoryPostCache()),
    Provider(create: (_) => const PostMapper()),

    Provider<PostRepository>(
      create: (ctx) => PostRepositoryImpl(
        api: ctx.read<PostApi>(),
        cache: ctx.read<PostCache>(),
        mapper: ctx.read<PostMapper>(),
      ),
    ),
  ];
}
```

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

## Migration guidance from current structure

When converting an existing folder like `app/models/post/*`:

-   Split into:
    -   `features/post/domain/entities/*` (canonical types used in UI)
    -   `features/post/data/models/*` (DTOs/cache models)
-   Move API services into:
    -   `features/post/data/data_sources/remote/*`
-   Add:
    -   `features/post/domain/repositories/post_repository.dart` (interface)
    -   `features/post/data/repositories/post_repository_impl.dart` (implementation)
    -   `features/post/data/mappers/*`

Repeat per feature.

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

## Type safety: Enums over strings

**CRITICAL RULE: Always use enums instead of hard-coded string values.**

### When to use enums

Use enums for any value that has a fixed set of possible values, such as:

-   Activity categories (Fitness, Work, Learning, Personal, Health, General)
-   Goal types (Fitness, Work, Learning, Personal, Health, Financial, General)
-   Travel activity types (driving, walking, cycling, running)
-   Status values (pending, completed, cancelled)
-   Pattern types (day_of_week, location, time, combined)
-   Any other fixed set of string constants

### Enum placement

-   **Domain enums**: Place in `features/<feature>/domain/value_objects/` or `features/<feature>/domain/enums/`
-   **Shared enums**: If used across multiple features, place in `core/enums/`

### Enum requirements

1. **All enums must have a `name` getter or extension** that returns the string representation for serialization
2. **All enums must have a `fromString` factory method** for deserialization
3. **Enums should be used in domain entities** instead of String fields
4. **Mappers must handle enum serialization/deserialization** when converting between DTOs and entities

### Example: ActivityType enum

```dart
// features/activity/domain/enums/activity_type.dart
enum ActivityType {
  fitness,
  work,
  learning,
  personal,
  health,
  general;

  String get displayName {
    switch (this) {
      case ActivityType.fitness:
        return 'Fitness';
      case ActivityType.work:
        return 'Work';
      case ActivityType.learning:
        return 'Learning';
      case ActivityType.personal:
        return 'Personal';
      case ActivityType.health:
        return 'Health';
      case ActivityType.general:
        return 'General';
    }
  }

  static ActivityType fromString(String value) {
    return ActivityType.values.firstWhere(
      (e) => e.name == value.toLowerCase() || e.displayName == value,
      orElse: () => ActivityType.general,
    );
  }
}
```

### Example: Using enum in entity

```dart
// features/activity/domain/entities/activity.dart
class Activity {
  final ActivityType category; // ✅ Use enum, not String

  const Activity({
    required this.category,
    // ...
  });
}
```

### Example: Enum serialization in mapper

```dart
// features/activity/data/mappers/activity_mapper.dart
class ActivityMapper {
  Activity fromModel(ActivityModel model) {
    return Activity(
      category: ActivityType.fromString(model.category), // ✅ Convert string to enum
      // ...
    );
  }

  ActivityModel toModel(Activity entity) {
    return ActivityModel(
      category: entity.category.name, // ✅ Convert enum to string for storage
      // ...
    );
  }
}
```

### Anti-patterns (avoid)

-   ❌ Using hard-coded strings like `'Fitness'`, `'Work'` instead of enums
-   ❌ Storing enum values as strings in domain entities
-   ❌ Comparing strings directly instead of using enum values
-   ❌ Creating lists of strings like `['Fitness', 'Work', 'Learning']` instead of `ActivityType.values`
-   UI imports DTOs directly
-   Provider performs Dio calls or JSON parsing
-   Provider contains business logic (should use usecases)
-   Repositories return DTOs to UI
-   Usecases import DTOs or data layer code
-   `post` feature imports `business/hive/event` features
-   Duplicate "posting systems" per context (business post vs hive post vs event post)

---

## Quick checklist for AI review

When analyzing code, confirm:

-   [ ] `core/` only contains shared plumbing and stable shared types
-   [ ] Features are under `features/<feature>/...` with domain/data/presentation
-   [ ] Repositories: interfaces in `domain/repositories`, impl in `data/repositories`
-   [ ] Usecases exist in `domain/usecases` for complex business logic (coordination, validation, rules)
-   [ ] UI uses domain entities, not DTOs
-   [ ] Mappers exist in `data/mappers` and isolate DTO↔Entity conversion
-   [ ] Providers contain UI state and call usecases/repositories; no Dio/DB/DTO parsing
-   [ ] Dependency direction is one-way (containers → capabilities)
-   [ ] Post context is represented via `PostContext` instead of separate post systems
-   [ ] **All fixed-value types use enums instead of hard-coded strings**
-   [ ] **Enums have proper serialization/deserialization methods**
-   [ ] **Domain entities use enum types, not String fields for categorical values**

---

## Notes

This is the target structure and rules. The current codebase can be migrated incrementally:

-   Create `core/` + `features/`
-   Move obvious core plumbing first
-   Migrate one feature completely (e.g., `post`) and use it as a template
-   Repeat feature-by-feature
