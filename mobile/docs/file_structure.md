# File Structure

_Last updated: 2025-12-26_

This document defines the **target file structure** for the Flutter mobile app using a **feature-sliced** structure with a shared **core** layer.

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

---

## Core vs Feature rule

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

See [core.md](./core.md) for detailed information about the core layer.

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

See [feature_implementation.md](./feature_implementation.md) for detailed information about implementing features.

---

## Related Documentation

-   [core.md](./core.md) - Core layer details
-   [feature_implementation.md](./feature_implementation.md) - Feature implementation patterns
-   [dependency_rules.md](./dependency_rules.md) - Dependency direction rules
-   [usecases.md](./usecases.md) - Usecase patterns

