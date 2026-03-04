# Usecases (Domain Business Logic)

_Last updated: 2025-12-26_

This document defines **usecases** and when/how to use them in the architecture.

---

## What is a usecase?

A usecase encapsulates a **single business operation** that orchestrates one or more repository calls and applies domain rules. Usecases live in the **domain layer** and are pure business logic—they don't know about HTTP, databases, or UI.

---

## When to use usecases vs repositories

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

---

## Usecase rules

-   Location: `features/<feature>/domain/usecases/`
-   Dependencies: Can depend on repository interfaces, entities, value objects, and other usecases within the same feature
-   Must NOT depend on: DTOs, data layer, presentation layer, or other features
-   Returns domain entities or `Result<T>` types
-   Pure business logic—no side effects beyond calling repositories

---

## Examples

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

---

## Usecase in provider flow

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

---

## Usecase dependency injection

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

### Benefits of ProxyProvider for usecases

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

### Example: Using a usecase in a screen

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

### Example: Using usecase in a provider

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

### Example: Testing with mocked usecase

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

### Alternative: Direct Provider (when usecase has no dependencies)

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

---

## Usecase vs Repository: Decision guide

| Scenario                                | Use Repository | Use Usecase |
| --------------------------------------- | -------------- | ----------- |
| Simple CRUD (get post by ID)            | ✅             | ❌          |
| Create post with validation             | ❌             | ✅          |
| Coordinate multiple repositories        | ❌             | ✅          |
| Apply business rules/filters            | ❌             | ✅          |
| Simple pagination                       | ✅             | ❌          |
| Personalized feed with filtering        | ❌             | ✅          |
| Conditional logic based on domain state | ❌             | ✅          |

---

## Anti-patterns (avoid)

-   ❌ Usecases that import DTOs or data layer code
-   ❌ Usecases that perform HTTP calls directly
-   ❌ Usecases that depend on other features' data layers
-   ❌ Providers that contain business logic instead of calling usecases
-   ❌ Usecases that are just pass-throughs to repositories (use repository directly)

---

## Related Documentation

-   [feature_implementation.md](./feature_implementation.md) - Repository pattern and data layer
-   [dependency_rules.md](./dependency_rules.md) - How usecases fit into dependency rules
