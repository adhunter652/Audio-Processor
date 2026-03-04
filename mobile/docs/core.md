# Core Layer

_Last updated: 2025-12-26_

This document defines what belongs in the **`core/`** layer and how it should be organized.

---

## What belongs in `core/`?

The `core/` layer contains **shared, cross-cutting concerns** used by multiple features. It should NOT contain feature-specific business logic.

### Core layer contents

1. **App plumbing**

    - Network client setup (Dio configuration)
    - Dependency injection wiring
    - Navigation/routing infrastructure
    - Platform method channels

2. **Cross-cutting services**

    - Analytics
    - Permissions
    - Session recording
    - Realtime/socket base client (if app-wide)

3. **Stable shared primitives**

    - `Result<T>` / `Failure` types
    - Pagination types
    - ID types
    - Error handling types

4. **Reusable UI system components**
    - Design system widgets (buttons, inputs, cards)
    - Theme configuration
    - Shared widgets used across many features

---

## Core layer structure

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

## Core layer rules

### ✅ DO put in `core/`:

-   Network client factory and interceptors
-   DI composition root (`core/di/app_providers.dart`)
-   Shared error types (`Result<T>`, `Failure`, `AppException`)
-   Navigation setup and route definitions
-   Analytics service interface and implementation
-   Permission service
-   Theme configuration
-   Shared design system widgets
-   Utility functions used by many features (date formatting, text utilities)

### ❌ DON'T put in `core/`:

-   Feature-specific business logic
-   Feature-specific entities or models
-   Feature-specific repositories or usecases
-   Feature-specific screens or widgets
-   DTOs or data models (these belong in `features/<feature>/data/models/`)

---

## Dependency injection in core

The `core/di/` folder contains the **composition root** where all dependencies are wired together.

### Example: App DI wiring

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
    // Core services
    Provider(create: (_) => DioClientFactory().create()),

    // Feature-specific providers
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

---

## Shared error types

`core/errors/` contains shared error handling types used across features:

-   `Result<T>` - Success/error wrapper
-   `Failure` - Error representation
-   `AppException` - Base exception type

These should be stable and not change frequently.

---

## Related Documentation

-   [file_structure.md](./file_structure.md) - Overall file structure
-   [feature_implementation.md](./feature_implementation.md) - How features use core
-   [dependency_rules.md](./dependency_rules.md) - How features depend on core
