# Dependency Rules

_Last updated: 2025-12-26_

This document defines the **dependency rules** that must be followed to maintain clean architecture boundaries.

---

## Layer dependency direction

Within a feature, layers must follow this dependency direction:

-   `presentation` → depends on `domain` (and optionally `core`)
-   `data` → depends on `domain` (implements domain contracts)
-   `domain` → depends on **nothing** Flutter-specific (no `BuildContext`, no Dio, no DB)

### Visual representation

```
presentation
    ↓
  domain  ←  data
    ↑
  core (optional)
```

### Rules

-   ✅ `presentation` can import `domain` entities, repositories, usecases
-   ✅ `presentation` can import `core` utilities, widgets, theme
-   ✅ `data` can import `domain` interfaces (repositories, entities)
-   ✅ `data` can import `core` network, storage, errors
-   ❌ `domain` must NOT import `presentation` or `data`
-   ❌ `domain` must NOT import Flutter-specific types (`BuildContext`, `Widget`, etc.)
-   ❌ `presentation` must NOT import `data` layer (DTOs, data_sources)

---

## Cross-feature dependency direction

Use a **container vs capability** model:

-   **Container features** (pages/tabs/ownership): `hive`, `business`, `event`
-   **Capability features** (reusable engines): `post`, `discussion`, `media`, `search`, `notification`

### Rules

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

## Dependency examples

### ✅ Good: Presentation depends on domain

```dart
// features/post/presentation/screens/post_list_screen.dart
import '../../../domain/entities/post.dart';  // ✅ OK
import '../../../domain/repositories/post_repository.dart';  // ✅ OK
import '../../../domain/usecases/get_personalized_feed_usecase.dart';  // ✅ OK
```

### ❌ Bad: Presentation imports data layer

```dart
// features/post/presentation/screens/post_list_screen.dart
import '../../../data/models/post_dto.dart';  // ❌ BAD - DTOs should not be in UI
import '../../../data/data_sources/remote/post_api.dart';  // ❌ BAD - data layer
```

### ✅ Good: Data implements domain contracts

```dart
// features/post/data/repositories/post_repository_impl.dart
import '../../domain/repositories/post_repository.dart';  // ✅ OK - implements interface
import '../../domain/entities/post.dart';  // ✅ OK - returns entities
```

### ❌ Bad: Domain imports data layer

```dart
// features/post/domain/repositories/post_repository.dart
import '../../data/models/post_dto.dart';  // ❌ BAD - domain must not know about DTOs
```

### ✅ Good: Container feature uses capability feature

```dart
// features/business/presentation/screens/business_posts_screen.dart
import '../../post/presentation/widgets/post_list_widget.dart';  // ✅ OK - composition
import '../../post/domain/repositories/post_repository.dart';  // ✅ OK - via DI
```

### ❌ Bad: Capability feature imports container

```dart
// features/post/domain/usecases/create_post_usecase.dart
import '../../business/domain/entities/business.dart';  // ❌ BAD - capability importing container
```

---

## Shared types across features

If multiple features need the same type, consider:

1. **Move to `core/`** if it's a stable, shared primitive (e.g., `PostContext`, `UserId`)
2. **Keep in one feature** and have others depend on it via domain interfaces
3. **Create a shared feature** if it's a significant shared domain concept

### Example: PostContext

If `PostContext` is used by many features, it can live in:

-   Option A: `features/post/domain/value_objects/post_context.dart` (if post feature owns it)
-   Option B: `core/refs/post_context.dart` (if truly shared across many features)

---

## Related Documentation

-   [file_structure.md](./file_structure.md) - Where code lives
-   [feature_implementation.md](./feature_implementation.md) - How features are structured
-   [usecases.md](./usecases.md) - Usecase dependencies
