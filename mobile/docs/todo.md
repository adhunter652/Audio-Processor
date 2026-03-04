Write tests for add record screen: ✓ COMPLETE
    ✓ make sure everything appears on the screen (use keys)
    ✓ make sure the editable widget includes evertything
    ✓ you can edit each field in the card and it updates
    ✓ saving a card moves to save activity
    ✓ push and pull show up and call the correct funtions
    ✓ date selector shows up and works correctly
    ✓ dropdowns work correctly

Write tests for add goal screen: ✓ COMPLETE
    ✓ make sure everything appears on the screen

write tests for each feature domain: ✓ COMPLETE
    ✓ Activity domain usecases (GetActivityOptionsUsecase)
    ✓ Goal domain usecases (GetGoalsUsecase, SaveGoalUsecase, DeleteGoalUsecase)
write tests for each core/widget: ✓ COMPLETE
    ✓ PillChip widget
    ✓ CompactIconButton widget
    ✓ LoadingWidget and LoadingOverlay
    ✓ SelectionBottomSheet

add feature to record and show users travels during the day: ✓ COMPLETE
    ✓ Created Travel entity and repository
    ✓ Created TravelsScreen to display daily travels
    ✓ Added location tracking packages (geolocator, geocoding)
    ✓ Created TravelTrackingService for automatic tracking
add feature to record the duration the user was driving each day through auto detection: ✓ COMPLETE
    ✓ Created TravelTrackingService with activity recognition
    ✓ Integrated driving detection using activity_recognition package
    ✓ Displays driving duration in TravelsScreen summary
add feature to predict how much sleep the user got each day: ✓ COMPLETE
    ✓ Created SleepRecord entity and repository
    ✓ Created SleepScreen to display sleep predictions
    ✓ Implemented sleep prediction algorithm based on historical data
    ✓ Shows predicted bedtime, wake time, and sleep duration
add navigation to the app, including user settings: ✓ COMPLETE
    ✓ Created MainNavigation with bottom navigation bar
    ✓ Created SettingsScreen with user profile, account management, and app settings
    ✓ Integrated navigation into AuthWrapper
add feature to check app usage of all apps on phone: ✓ COMPLETE
    ✓ Created AppUsage entity and repository
    ✓ Created AppUsageScreen to display daily app usage statistics
    ✓ Created AppUsageTrackingService to fetch usage from system
    ✓ Shows total usage time, number of apps used, and individual app usage