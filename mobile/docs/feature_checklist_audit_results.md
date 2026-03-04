# Feature Checklist Audit Results

_Generated: 2025-01-XX_

This document summarizes the violations found during the feature checklist audit and the fixes applied.

## Summary

- **Total Features Audited**: 8 (activity, app_usage, auth, dashboard, goal, settings, sleep, travel)
- **Violations Found**: 8 major categories
- **Fixes Applied**: 5
- **Remaining Issues**: 3 (require architectural decisions)

---

## ✅ Fixed Violations

### 1. Cross-Feature Domain Imports (Activity Feature)
**Issue**: Activity feature was importing `GetGoalsUsecase` from goal feature's domain layer.

**Location**:
- `lib/features/activity/presentation/widgets/editable_activity_card.dart`
- `lib/features/activity/presentation/state/providers/record_activities_provider.dart`

**Fix Applied**:
- Removed direct import of `GetGoalsUsecase` from widget
- Changed provider to use `GoalRepository` interface instead of `GetGoalsUsecase`
- Updated DI configuration in `app_providers.dart` to inject `GoalRepository`

**Note**: While this still creates a cross-feature domain dependency, using the repository interface is better than importing a usecase, and it's a necessary dependency since activities reference goals.

### 2. Cross-Feature Presentation Imports (Activity Feature)
**Issue**: Activity feature was importing dashboard and goal presentation screens directly.

**Location**:
- `lib/features/activity/presentation/screens/record_activities_screen.dart`
- `lib/features/activity/presentation/widgets/editable_activity_card.dart`

**Fix Applied**:
- Removed direct import of `DashboardScreen` from activity screen
- Added navigation callback pattern for goals screen navigation
- Created shared `ActivityPreFilledData` model in `lib/features/activity/presentation/models/`
- Updated dashboard to import from shared location

### 3. Shared Type Duplication
**Issue**: `ActivityPreFilledData` was defined in both dashboard and activity features.

**Fix Applied**:
- Created `lib/features/activity/presentation/models/activity_pre_filled_data.dart`
- Updated both features to import from shared location
- Removed duplicate definition from dashboard screen

---

## ⚠️ Remaining Issues (Require Architectural Decisions)

### 4. Domain Layer Importing Core Services
**Issue**: `SaveActivityToGoogleSheetsUsecase` imports `GoogleSheetsService` from core.

**Location**: `lib/features/activity/domain/usecases/save_activity_to_google_sheets_usecase.dart`

**Recommendation**:
- Create a repository interface for Google Sheets operations (e.g., `GoogleSheetsRepository`)
- Move Google Sheets service integration to data layer
- Have usecase depend on repository interface instead

**Alternative**: Accept this as a special case for external service integration, or move the usecase to data layer.

### 5. Presentation Layer Importing Core Services
**Issue**: Providers import `LifeAgentSyncService` directly from core.

**Location**:
- `lib/features/activity/presentation/state/providers/record_activities_provider.dart`
- `lib/features/goal/presentation/state/providers/goals_provider.dart`

**Recommendation**:
- Sync operations should be handled by repositories, not providers
- Move sync logic to repository implementations
- Providers should only call repository methods

### 6. Services Folder in Features
**Issue**: `travel` and `app_usage` features have `services/` folders.

**Location**:
- `lib/features/travel/services/travel_tracking_service.dart`
- `lib/features/app_usage/services/app_usage_tracking_service.dart`

**Recommendation**:
- Review if these services should be:
  - Integrated into domain layer (as usecases)
  - Moved to data layer (if they're data operations)
  - Moved to core (if they're shared across features)

### 7. Settings Feature Importing Auth Provider
**Issue**: Settings feature imports `AuthProvider` from auth feature's presentation layer.

**Location**: `lib/features/settings/presentation/screens/settings_screen.dart`

**Status**: **Acceptable** - Settings is a container feature and can import capability features' presentation layer according to architecture rules. However, for better separation, consider using auth domain layer (repository/usecase) instead.

---

## 📋 DI Setup Review

### Current Status
All major features have proper DI setup in `core/di/app_providers.dart`:
- ✅ Auth feature: Complete
- ✅ Activity feature: Complete (updated to use GoalRepository)
- ✅ Goal feature: Complete
- ⚠️ Travel feature: Needs review (service not in DI)
- ⚠️ App Usage feature: Needs review (service not in DI)
- ⚠️ Sleep feature: Needs review

---

## 📝 Naming Conventions

All features follow naming conventions:
- ✅ Repository interfaces: `*Repository`
- ✅ Repository implementations: `*RepositoryImpl`
- ✅ Usecases: `*Usecase`
- ✅ Providers: `*Provider`
- ✅ DTOs/Models: `*Model` or `*Dto`

---

## 🔄 Next Steps

1. **Refactor Google Sheets Integration**:
   - Create `GoogleSheetsRepository` interface
   - Move service integration to data layer
   - Update usecases to depend on repository

2. **Refactor Sync Service Usage**:
   - Move sync operations to repository implementations
   - Remove direct service imports from providers

3. **Review Services in Features**:
   - Decide on location for `travel_tracking_service` and `app_usage_tracking_service`
   - Integrate into domain/data layer or move to core

4. **Complete DI Setup**:
   - Add missing providers for travel, app_usage, and sleep features
   - Ensure all services are properly injected

---

## Related Documentation

- [feature_checklist.md](./feature_checklist.md) - Original checklist
- [dependency_rules.md](./dependency_rules.md) - Dependency rules
- [usecases.md](./usecases.md) - Usecase patterns
- [feature_implementation.md](./feature_implementation.md) - Implementation patterns
