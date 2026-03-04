import 'package:flutter/material.dart';

/// App theme: organized palette and typography. Defaults to dark mode.
class AppTheme {
  AppTheme._();

  static const Color _primary = Color(0xFF7C4DFF);
  static const Color _primaryVariant = Color(0xFF651FFF);
  static const Color _surfaceDark = Color(0xFF121212);
  static const Color _surfaceVariantDark = Color(0xFF1E1E1E);
  static const Color _onSurfaceDark = Color(0xFFE1E1E1);
  static const Color _onSurfaceVariantDark = Color(0xFFB0B0B0);
  static const Color _error = Color(0xFFCF6679);
  static const Color _outline = Color(0xFF3D3D3D);

  /// Dark theme (default).
  static ThemeData get dark {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: const ColorScheme.dark(
        primary: _primary,
        primaryContainer: _primaryVariant,
        surface: _surfaceDark,
        surfaceContainerHighest: _surfaceVariantDark,
        onSurface: _onSurfaceDark,
        onSurfaceVariant: _onSurfaceVariantDark,
        error: _error,
        outline: _outline,
      ),
      appBarTheme: const AppBarTheme(
        centerTitle: true,
        elevation: 0,
        backgroundColor: _surfaceDark,
        foregroundColor: _onSurfaceDark,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: _surfaceVariantDark,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: _outline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: _primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: _error),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        hintStyle: const TextStyle(color: _onSurfaceVariantDark),
      ),
      searchBarTheme: SearchBarThemeData(
        backgroundColor: MaterialStateProperty.all(_surfaceVariantDark),
        elevation: MaterialStateProperty.all(0),
        padding: MaterialStateProperty.all(const EdgeInsets.symmetric(horizontal: 16, vertical: 12)),
        shape: MaterialStateProperty.all(RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
      ),
      cardTheme: CardThemeData(
        color: _surfaceVariantDark,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  /// Light theme (optional).
  static ThemeData get light {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.light(
        primary: _primary,
        primaryContainer: _primaryVariant,
        surface: Colors.white,
        onSurface: const Color(0xFF1C1C1C),
        onSurfaceVariant: const Color(0xFF5C5C5C),
        error: _error,
        outline: const Color(0xFFE0E0E0),
      ),
      appBarTheme: const AppBarTheme(
        centerTitle: true,
        elevation: 0,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      searchBarTheme: SearchBarThemeData(
        elevation: MaterialStateProperty.all(0),
        padding: MaterialStateProperty.all(const EdgeInsets.symmetric(horizontal: 16, vertical: 12)),
        shape: MaterialStateProperty.all(RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}
