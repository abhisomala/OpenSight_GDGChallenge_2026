// Unit tests for SettingsController defaults + change notifications, and the
// high-contrast text helper in app_theme.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_client/settings_controller.dart';
import 'package:voice_client/ui/app_theme.dart';

void main() {
  group('SettingsController', () {
    test('defaults match the Figma', () {
      final s = SettingsController();
      expect(s.geminiModel, 'Gemini 2.5 Flash');
      expect(s.screenReaderMode, isFalse);
      expect(s.announceAgentChanges, isTrue);
      expect(s.hapticFeedback, isTrue);
      expect(s.highContrastText, isFalse);
    });

    test('each setter notifies listeners when the value changes', () {
      final s = SettingsController();
      int notifications = 0;
      s.addListener(() => notifications++);

      s.screenReaderMode = true;
      s.announceAgentChanges = false;
      s.hapticFeedback = false;
      s.highContrastText = true;
      s.geminiModel = 'Gemini Pro';

      expect(notifications, 5);
      expect(s.screenReaderMode, isTrue);
      expect(s.announceAgentChanges, isFalse);
      expect(s.hapticFeedback, isFalse);
      expect(s.highContrastText, isTrue);
      expect(s.geminiModel, 'Gemini Pro');
    });

    test('setting the same value does not notify', () {
      final s = SettingsController();
      int notifications = 0;
      s.addListener(() => notifications++);
      s.hapticFeedback = true; // already true
      expect(notifications, 0);
    });
  });

  group('AppText high-contrast helpers', () {
    test('bodyFor brightens color and strengthens weight when on', () {
      final TextStyle normal = AppText.bodyFor(false);
      final TextStyle high = AppText.bodyFor(true);
      expect(high.color, isNot(normal.color));
      expect(high.color, AppColors.textPrimaryHigh);
      expect(high.fontWeight, FontWeight.w600);
    });

    test('captionFor brightens the secondary color when on', () {
      final TextStyle normal = AppText.captionFor(false);
      final TextStyle high = AppText.captionFor(true);
      expect(high.color, isNot(normal.color));
      expect(high.color, AppColors.textDimHigh);
    });
  });
}
