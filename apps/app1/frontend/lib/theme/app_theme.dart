import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/theme/app_colors.dart';

abstract final class AppTheme {
  static const maxContentWidth = 430.0;

  static ThemeData get light {
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: AppColors.cream,
      fontFamily: GoogleFonts.poppins().fontFamily,
      colorScheme: const ColorScheme.light(
        primary: AppColors.pinkDeep,
        onPrimary: AppColors.cream,
        secondary: AppColors.tan,
        onSecondary: AppColors.cream,
        surface: AppColors.cream,
        onSurface: AppColors.dark,
        outline: AppColors.brown,
      ),
      textTheme: TextTheme(
        displayLarge: GoogleFonts.lora(
          fontSize: 44,
          fontWeight: FontWeight.w600,
          fontStyle: FontStyle.italic,
          color: AppColors.dark,
          height: 1.1,
        ),
        displayMedium: GoogleFonts.lora(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          fontStyle: FontStyle.italic,
          color: AppColors.dark,
          height: 1.1,
        ),
        headlineSmall: GoogleFonts.lora(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: AppColors.dark,
          height: 1.2,
        ),
        titleMedium: GoogleFonts.lora(
          fontSize: 15,
          fontWeight: FontWeight.w600,
          color: AppColors.dark,
          height: 1.25,
        ),
        bodyMedium: GoogleFonts.poppins(
          fontSize: 15,
          fontWeight: FontWeight.w400,
          color: AppColors.brown,
          height: 1.45,
        ),
        bodyLarge: GoogleFonts.poppins(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: AppColors.dark,
        ),
        labelSmall: GoogleFonts.poppins(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.8,
          color: AppColors.brown,
        ),
        labelLarge: GoogleFonts.poppins(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: AppColors.cream,
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.cream,
        foregroundColor: AppColors.dark,
        elevation: 0,
        scrolledUnderElevation: 0,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.white,
        hintStyle: GoogleFonts.poppins(
          fontSize: 15,
          color: AppColors.brown.withValues(alpha: 0.55),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: AppColors.brown.withValues(alpha: 0.18)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: AppColors.brown.withValues(alpha: 0.18)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.tan, width: 1.5),
        ),
      ),
    );
  }
}
