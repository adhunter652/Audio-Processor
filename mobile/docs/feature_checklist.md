# Feature Architecture Checklist

_Last updated: 2025-12-26_

This checklist is designed for **AI code review** to verify that a feature follows all architecture requirements and policies. Use this when reviewing or implementing a feature.

---

## How to Use This Checklist

1. **For each feature**, go through all sections systematically
2. **Check each item** - verify it's implemented correctly or identify violations
3. **Report violations** with specific file paths and line numbers
4. **Suggest fixes** based on the architecture documentation

---

## 1. File Structure

### 1.1 Feature Location

-   [ ] Feature is located under `features/<feature_name>/` (not in `app/` or `lib/`)
-   [ ] Feature name is lowercase, singular (e.g., `post`, `business`, `hive`)
-   [ ] No feature-specific code exists in `core/` (except shared types moved to core)

### 1.2 Feature Folder Structure

-   [ ] Feature has `domain/` folder with subfolders:
    -   [ ] `domain/entities/`
    -   [ ] `domain/value_objects/` (if needed)
    -   [ ] `domain/repositories/`
    -   [ ] `domain/usecases/` (if needed)
-   [ ] Feature has `data/` folder with subfolders:
    -   [ ] `data/models/` (DTOs only)
    -   [ ] `data/data_sources/remote/`
    -   [ ] `data/data_sources/local/` (if needed)
    -   [ ] `data/mappers/`
    -   [ ] `data/repositories/`
-   [ ] Feature has `presentation/` folder with subfolders:
    -   [ ] `presentation/screens/`
    -   [ ] `presentation/widgets/`
    -   [ ] `presentation/state/providers/` (or `blocs/`, `cubits/`)
    -   [ ] `presentation/validators/` (if needed)
    -   [ ] `presentation/utils/` (UI helpers only)

### 1.3 Core Layer Check

-   [ ] No feature-specific business logic in `core/`
-   [ ] Feature-specific tables/models are NOT in `core/storage/local_database/`
-   [ ] Only shared, cross-cutting code is in `core/`

---

## 2. Domain Layer

### 2.1 Entities

-   [ ] Entities are in `features/<feature>/domain/entities/`
-   [ ] Entities are pure Dart classes (no JSON annotations like `@JsonSerializable`)
-   [ ] Entities do NOT import:
    -   [ ] DTOs
    -   [ ] Dio/HTTP packages
    -   [ ] Database packages
    -   [ ] Flutter UI packages (`package:flutter/material.dart` is OK for basic types)
-   [ ] Entities have convenient, domain-friendly property names (not API field names)
-   [ ] Entities are immutable (use `final` fields, `const` constructors when possible)

### 2.2 Value Objects

-   [ ] Value objects are in `features/<feature>/domain/value_objects/`
-   [ ] Value objects follow same rules as entities (no DTOs, no Flutter-specific imports)
-   [ ] Value objects are small, focused types (IDs, context objects, small domain types)

### 2.3 Repository Interfaces

-   [ ] Repository interfaces are in `features/<feature>/domain/repositories/`
-   [ ] Repository interfaces are `abstract class` (not interfaces in Dart)
-   [ ] Repository interfaces return domain entities (or `Result<T>` of entities)
-   [ ] Repository interfaces do NOT reference:
    -   [ ] DTOs
    -   [ ] Dio/HTTP
    -   [ ] DB APIs
    -   [ ] Flutter UI types
-   [ ] Repository interfaces have clear, domain-focused method names
-   [ ] Repository interfaces are stable (don't change frequently)

### 2.4 Usecases

-   [ ] Usecases are in `features/<feature>/domain/usecases/` (if they exist)
-   [ ] Usecases are only created when needed (coordination, validation, business rules)
-   [ ] Usecases do NOT import:
    -   [ ] DTOs
    -   [ ] Data layer code
    -   [ ] Presentation layer code
    -   [ ] Other features' data layers
-   [ ] Usecases depend only on:
    -   [ ] Repository interfaces
    -   [ ] Domain entities
    -   [ ] Value objects
    -   [ ] Other usecases in the same feature
-   [ ] Usecases return domain entities or `Result<T>`
-   [ ] Usecases are NOT just pass-throughs to repositories (use repository directly if no logic)

---

## 3. Data Layer

### 3.1 DTOs (Data Transfer Objects)

-   [ ] DTOs are in `features/<feature>/data/models/`
-   [ ] DTOs mirror API JSON structure (use API field names like `author_id`, `created_at`)
-   [ ] DTOs have `fromJson` factory constructors
-   [ ] DTOs are separate from domain entities (no mixing)
-   [ ] DTOs are NOT imported by:
    -   [ ] Domain layer
    -   [ ] Presentation layer
    -   [ ] UI code

### 3.2 Mappers

-   [ ] Mappers are in `features/<feature>/data/mappers/`
-   [ ] Mappers are the ONLY code that imports both DTOs and Entities
-   [ ] Mappers convert DTO → Entity (and LocalModel → Entity if needed)
-   [ ] Mappers handle field name translation (API names → domain names)
-   [ ] Mappers handle type conversions (e.g., ISO strings → DateTime)

### 3.3 Remote data_sources

-   [ ] Remote data_sources are in `features/<feature>/data/data_sources/remote/`
-   [ ] Remote data_sources are abstract classes or interfaces
-   [ ] Remote data_sources return DTOs (not entities)
-   [ ] Remote data_sources use `core/network/dio_client.dart` (not direct Dio)
-   [ ] Remote data_sources do NOT import domain entities directly

### 3.4 Local data_sources

-   [ ] Local data_sources are in `features/<feature>/data/data_sources/local/` (if needed)
-   [ ] Local data_sources handle caching/DB operations
-   [ ] Feature-specific tables are in the feature's data layer (not in `core/storage/`)

### 3.5 Repository Implementations

-   [ ] Repository implementations are in `features/<feature>/data/repositories/`
-   [ ] Repository implementations implement domain repository interfaces
-   [ ] Repository implementations orchestrate:
    -   [ ] Remote datasource (API)
    -   [ ] Local datasource (cache/DB)
    -   [ ] Mappers (DTO→Entity conversion)
-   [ ] Repository implementations return domain entities (not DTOs)
-   [ ] Repository implementations handle caching strategy (cache-first, stale-while-revalidate, etc.)
-   [ ] Repository implementations translate errors to `Failure`/`AppException`

---

## 4. Presentation Layer

### 4.1 Screens and Widgets

-   [ ] Screens are in `features/<feature>/presentation/screens/`
-   [ ] Widgets are in `features/<feature>/presentation/widgets/`
-   [ ] Presentation code imports:
    -   [ ] Domain entities (✅)
    -   [ ] Domain repositories (via DI) (✅)
    -   [ ] Domain usecases (via DI) (✅)
    -   [ ] Core utilities/widgets (✅)
-   [ ] Presentation code does NOT import:
    -   [ ] DTOs (❌)
    -   [ ] Data layer data_sources (❌)
    -   [ ] Data layer mappers (❌)

### 4.2 State Management (Providers)

-   [ ] Providers are in `features/<feature>/presentation/state/providers/`
-   [ ] Providers extend `ChangeNotifier` (or use Bloc/Cubit if preferred)
-   [ ] Providers contain ONLY:
    -   [ ] UI state (loading, error, items list, etc.)
    -   [ ] Calls to repositories/usecases
-   [ ] Providers do NOT contain:
    -   [ ] Dio calls (❌)
    -   [ ] DB queries (❌)
    -   [ ] DTO parsing/mapping (❌)
    -   [ ] Complex business logic (should be in usecases) (❌)
-   [ ] Providers are injected via DI (not manually created)

### 4.3 Validators

-   [ ] Validators are in `features/<feature>/presentation/validators/` (if needed)
-   [ ] Validators are for UI-level validation only (not business rules)
-   [ ] Business validation rules are in usecases, not validators

---

## 5. Dependency Rules

### 5.1 Layer Dependencies

-   [ ] `presentation` → depends on `domain` (✅)
-   [ ] `presentation` → depends on `core` (optional, ✅)
-   [ ] `data` → depends on `domain` (✅)
-   [ ] `data` → depends on `core` (network, storage, errors) (✅)
-   [ ] `domain` → does NOT depend on `presentation` (❌)
-   [ ] `domain` → does NOT depend on `data` (❌)
-   [ ] `domain` → does NOT depend on Flutter-specific types (❌)

### 5.2 Cross-Feature Dependencies

-   [ ] Feature type is identified:
    -   [ ] Container feature (hive, business, event) OR
    -   [ ] Capability feature (post, discussion, media, search, notification)
-   [ ] If container feature:
    -   [ ] Can import capability features (✅)
    -   [ ] Can compose capability widgets (✅)
-   [ ] If capability feature:
    -   [ ] Does NOT import container features (❌)
    -   [ ] Does NOT import other features' data layers (❌)
-   [ ] Cross-feature domain imports are avoided (use `core/` for shared types if needed)

### 5.3 Import Verification

Check all import statements in the feature:

-   [ ] No `import '../../data/models/*.dto.dart'` in presentation layer
-   [ ] No `import '../../data/data_sources/*'` in presentation layer
-   [ ] No `import '../../data/models/*.dto.dart'` in domain layer
-   [ ] No `import '../../presentation/*'` in domain layer
-   [ ] No `import '../../presentation/*'` in data layer
-   [ ] No `import 'features/<other_container>/*'` in capability features

---

## 6. Dependency Injection

### 6.1 DI Setup

-   [ ] All dependencies are wired in `core/di/app_providers.dart`
-   [ ] Repository implementations are provided
-   [ ] Usecases are provided (using `ProxyProvider` if they have dependencies)
-   [ ] data_sources (API, Cache) are provided
-   [ ] Mappers are provided

### 6.2 Provider Usage

-   [ ] Providers access dependencies via `Provider.of<T>(context)` or constructor injection
-   [ ] No manual dependency creation in screens/widgets
-   [ ] Dependencies are injected, not instantiated directly

---

## 7. Naming Conventions

### 7.1 File and Class Naming

-   [ ] Repository interfaces: `*Repository` (e.g., `PostRepository`)
-   [ ] Repository implementations: `*RepositoryImpl` (e.g., `PostRepositoryImpl`)
-   [ ] Usecases: `*Usecase` (e.g., `CreatePostUsecase`)
-   [ ] API/data_sources: `*Api` or `*RemoteDataSource` (e.g., `PostApi`)
-   [ ] Cache/data_sources: `*Cache` or `*LocalDataSource` (e.g., `PostCache`)
-   [ ] DTOs: `*Dto` (e.g., `PostDto`)
-   [ ] Mappers: `*Mapper` (e.g., `PostMapper`)
-   [ ] Providers: `*Provider` (e.g., `PostFeedProvider`)

### 7.2 Method Naming

-   [ ] Repository methods use domain language (e.g., `getPost`, `createPost`)
-   [ ] Usecase methods are `execute()` (or descriptive names)
-   [ ] Provider methods are action-oriented (e.g., `loadInitial`, `loadMore`, `submitPost`)

---

## 8. Feature-Specific Patterns

### 8.1 Post Feature (if applicable)

-   [ ] Uses `PostContext` instead of separate "BusinessPost/HivePost/EventPost" systems
-   [ ] `PostContext` is a sealed class with variants (HivePostContext, BusinessPostContext, etc.)
-   [ ] Same post screens/widgets are reused with different contexts

### 8.2 Feature Splitting

-   [ ] Feature is not split by context (e.g., not "hive_posts" and "business_posts" as separate features)
-   [ ] Feature represents a single capability/bounded context
-   [ ] Related capabilities are in the same feature or properly separated

---

## 9. Code Quality

### 9.1 Separation of Concerns

-   [ ] Business logic is in usecases or repositories (not in providers)
-   [ ] Data transformation is in mappers (not scattered)
-   [ ] UI logic is in presentation layer (not in domain/data)

### 9.2 Error Handling

-   [ ] Errors are translated to domain types (`Failure`, `AppException`)
-   [ ] Repository implementations handle and translate errors
-   [ ] Presentation layer handles errors appropriately

### 9.3 Testing

-   [ ] Domain layer is easily testable (no Flutter dependencies)
-   [ ] Repository interfaces can be mocked
-   [ ] Usecases can be tested in isolation

---

## 10. Anti-Patterns Check

Verify the feature does NOT have:

-   [ ] UI importing DTOs directly
-   [ ] Provider performing Dio calls or JSON parsing
-   [ ] Provider containing business logic (should use usecases)
-   [ ] Repositories returning DTOs to UI
-   [ ] Usecases importing DTOs or data layer code
-   [ ] Capability features importing container features
-   [ ] Duplicate "posting systems" per context (business post vs hive post vs event post)
-   [ ] Domain layer importing Flutter-specific types
-   [ ] Feature-specific code in `core/`
-   [ ] Manual dependency creation instead of DI

---

## Summary Template

After reviewing a feature, provide a summary:

```
## Feature: <feature_name>

### ✅ Passed Checks
- [List items that passed]

### ❌ Violations Found
- [List violations with file paths and line numbers]

### 🔧 Suggested Fixes
- [List specific fixes needed]

### 📝 Notes
- [Any additional observations]
```

---

## Related Documentation

-   [file_structure.md](./file_structure.md) - File structure requirements
-   [core.md](./core.md) - Core layer rules
-   [feature_implementation.md](./feature_implementation.md) - Implementation patterns
-   [usecases.md](./usecases.md) - Usecase patterns
-   [dependency_rules.md](./dependency_rules.md) - Dependency rules
-   [migration.md](./migration.md) - Migration patterns
