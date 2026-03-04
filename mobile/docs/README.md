# HubHive Flutter App Architecture Documentation

_Last updated: 2025-12-26_

This documentation defines the **target architecture** for the Flutter mobile app using a **feature-sliced** structure with a shared **core** layer (Option A).  
It is written to be **AI-friendly**: clear rules, dependency directions, folder conventions, and code examples so an AI can compare the current implementation against this target and suggest concrete changes.

---

## Goals

-   Keep code **modular**, **testable**, and **easy to evolve**.
-   Prevent a "overlord `app/` folder" where everything depends on everything.
-   Make ownership obvious: **feature code lives with the feature**, cross-cutting concerns live in **core**.
-   Enforce boundaries so refactors don't cascade through the entire codebase.

---

## Documentation Structure

This documentation is split into focused files:

### Core Documentation

-   **[file_structure.md](./file_structure.md)** - High-level structure, folder layouts, core vs feature rules
-   **[core.md](./core.md)** - Core layer details: what belongs in core, DI setup, shared types
-   **[feature_implementation.md](./feature_implementation.md)** - How to implement features: repositories, mappers, providers, flows
-   **[usecases.md](./usecases.md)** - Usecase patterns: when to use, examples, dependency injection
-   **[dependency_rules.md](./dependency_rules.md)** - Dependency direction rules: layer dependencies, cross-feature rules
-   **[migration.md](./migration.md)** - Migration guidance: how to convert existing code to target architecture
-   **[feature_checklist.md](./feature_checklist.md)** - **AI code review checklist** to verify features follow architecture requirements

---

## Quick Start

1. **New to the architecture?** Start with [file_structure.md](./file_structure.md) to understand the overall structure.
2. **Implementing a feature?** Read [feature_implementation.md](./feature_implementation.md) for patterns.
3. **Adding business logic?** Check [usecases.md](./usecases.md) to decide if you need a usecase.
4. **Migrating existing code?** Follow [migration.md](./migration.md) for step-by-step guidance.
5. **Reviewing a feature?** Use [feature_checklist.md](./feature_checklist.md) to verify architecture compliance.

---

## Quick Checklist for AI Review

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

---

## Anti-patterns (avoid)

-   UI imports DTOs directly
-   Provider performs Dio calls or JSON parsing
-   Provider contains business logic (should use usecases)
-   Repositories return DTOs to UI
-   Usecases import DTOs or data layer code
-   `post` feature imports `business/hive/event` features
-   Duplicate "posting systems" per context (business post vs hive post vs event post)

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

## Related Files

-   [architecture.md](../architecture.md) - Original single-file architecture document (may be outdated)

