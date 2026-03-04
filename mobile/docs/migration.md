# Migration Guidance

_Last updated: 2025-12-26_

This document provides guidance for migrating from the current codebase structure to the target architecture.

---

## Migration strategy

This is the target structure and rules. The current codebase can be migrated incrementally:

1. Create `core/` + `features/`
2. Move obvious core plumbing first
3. Migrate one feature completely (e.g., `post`) and use it as a template
4. Repeat feature-by-feature

---

## Converting existing code

When converting an existing folder like `app/models/post/*`:

### Step 1: Split models

Split into:

-   `features/post/domain/entities/*` (canonical types used in UI)
-   `features/post/data/models/*` (DTOs/cache models)

**Before:**

```
app/models/post/post.dart  # Mixed entity/DTO
```

**After:**

```
features/post/domain/entities/post.dart  # Pure domain entity
features/post/data/models/post_dto.dart  # API DTO
```

### Step 2: Move API services

Move API services into:

-   `features/post/data/data_sources/remote/*`

**Before:**

```
app/services/post_service.dart
```

**After:**

```
features/post/data/data_sources/remote/post_api.dart
```

### Step 3: Add repository pattern

Add:

-   `features/post/domain/repositories/post_repository.dart` (interface)
-   `features/post/data/repositories/post_repository_impl.dart` (implementation)

The repository implementation wraps the API service and adds caching/mapping logic.

### Step 4: Add mappers

Add:

-   `features/post/data/mappers/*`

Mappers convert between DTOs and domain entities.

### Step 5: Update providers

Update providers to:

-   Use repository interfaces instead of direct API calls
-   Call usecases when business logic is needed
-   Remove Dio/DB/DTO parsing logic

---

## Migration checklist per feature

When migrating a feature:

-   [ ] Create `features/<feature>/domain/entities/` with domain models
-   [ ] Create `features/<feature>/data/models/` with DTOs
-   [ ] Create `features/<feature>/data/mappers/` for DTO↔Entity conversion
-   [ ] Create `features/<feature>/domain/repositories/` with interfaces
-   [ ] Create `features/<feature>/data/data_sources/remote/` for API clients
-   [ ] Create `features/<feature>/data/data_sources/local/` for cache/DB
-   [ ] Create `features/<feature>/data/repositories/` with implementations
-   [ ] Create `features/<feature>/domain/usecases/` for complex business logic (if needed)
-   [ ] Update `features/<feature>/presentation/` to use domain entities and repositories/usecases
-   [ ] Remove DTO imports from presentation layer
-   [ ] Wire dependencies in `core/di/app_providers.dart`

---

## Common migration patterns

### Pattern 1: Model → Entity + DTO

**Before:**

```dart
// app/models/post.dart
class Post {
  final String id;
  final String authorId;
  final String body;  // API field name
  final DateTime createdAt;

  Post.fromJson(Map<String, dynamic> json) { ... }
}
```

**After:**

```dart
// features/post/domain/entities/post.dart
class Post {
  final String id;
  final String authorId;
  final String text;  // Domain-friendly name
  final DateTime createdAt;
}

// features/post/data/models/post_dto.dart
class PostDto {
  final String id;
  final String author_id;  // API field name
  final String body;
  final String created_at;

  factory PostDto.fromJson(Map<String, dynamic> json) { ... }
}

// features/post/data/mappers/post_mapper.dart
class PostMapper {
  Post fromDto(PostDto dto) {
    return Post(
      id: dto.id,
      authorId: dto.author_id,
      text: dto.body,
      createdAt: DateTime.parse(dto.created_at),
    );
  }
}
```

### Pattern 2: Service → Repository

**Before:**

```dart
// app/services/post_service.dart
class PostService {
  Future<Post> getPost(String id) async {
    final response = await dio.get('/posts/$id');
    return Post.fromJson(response.data);
  }
}
```

**After:**

```dart
// features/post/domain/repositories/post_repository.dart
abstract class PostRepository {
  Future<Post> getPost(String postId);
}

// features/post/data/repositories/post_repository_impl.dart
class PostRepositoryImpl implements PostRepository {
  final PostApi _api;
  final PostMapper _mapper;

  @override
  Future<Post> getPost(String postId) async {
    final dto = await _api.fetchPost(postId);
    return _mapper.fromDto(dto);
  }
}
```

### Pattern 3: Provider with business logic → Provider + Usecase

**Before:**

```dart
// app/providers/post_provider.dart
class PostProvider extends ChangeNotifier {
  Future<void> createPost(String text) async {
    // Business logic in provider ❌
    if (text.length > 5000) {
      throw Error('Text too long');
    }
    await _service.createPost(text);
  }
}
```

**After:**

```dart
// features/post/domain/usecases/create_post_usecase.dart
class CreatePostUsecase {
  Future<Post> execute(String text) async {
    if (text.length > 5000) {
      throw ArgumentError('Text too long');
    }
    return await _repository.createPost(text);
  }
}

// features/post/presentation/state/providers/post_provider.dart
class PostProvider extends ChangeNotifier {
  final CreatePostUsecase _usecase;

  Future<void> createPost(String text) async {
    await _usecase.execute(text);  // Business logic in usecase ✅
  }
}
```

---

## Anti-patterns to avoid during migration

-   ❌ Moving code without splitting entities/DTOs
-   ❌ Keeping business logic in providers
-   ❌ Allowing UI to import DTOs
-   ❌ Skipping the repository pattern
-   ❌ Creating usecases that are just pass-throughs
-   ❌ Mixing domain and data concerns

---

## Related Documentation

-   [file_structure.md](./file_structure.md) - Target structure
-   [feature_implementation.md](./feature_implementation.md) - Implementation patterns
-   [usecases.md](./usecases.md) - Usecase patterns
