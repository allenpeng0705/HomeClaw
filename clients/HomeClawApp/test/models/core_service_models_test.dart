import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/models/core_service_models.dart';

void main() {
  group('SandboxListEntry', () {
    test('fromJson creates valid instance', () {
      final json = {'name': 'test.txt', 'type': 'file', 'path': '/home/user/test.txt'};
      final entry = SandboxListEntry(
        name: json['name']!,
        type: json['type']!,
        path: json['path']!,
      );
      expect(entry.name, 'test.txt');
      expect(entry.type, 'file');
      expect(entry.path, '/home/user/test.txt');
    });
  });

  group('SandboxListResult', () {
    test('fromJson creates valid instance', () {
      final entries = [
        SandboxListEntry(name: 'a.txt', type: 'file', path: '/a.txt'),
        SandboxListEntry(name: 'b', type: 'dir', path: '/b'),
      ];
      final result = SandboxListResult(
        scope: 'user',
        path: '/home/user',
        entries: entries,
      );
      expect(result.scope, 'user');
      expect(result.path, '/home/user');
      expect(result.entries.length, 2);
    });
  });

  group('BridgeProjectListEntry', () {
    test('fromJson creates valid instance', () {
      final entry = BridgeProjectListEntry(
        name: 'main.dart',
        type: 'file',
        relPath: 'lib/main.dart',
        absPath: '/project/lib/main.dart',
        size: 1024,
      );
      expect(entry.name, 'main.dart');
      expect(entry.type, 'file');
      expect(entry.relPath, 'lib/main.dart');
      expect(entry.absPath, '/project/lib/main.dart');
      expect(entry.size, 1024);
    });

    test('size is nullable', () {
      final entry = BridgeProjectListEntry(
        name: 'main.dart',
        type: 'file',
        relPath: 'lib/main.dart',
        absPath: '/project/lib/main.dart',
      );
      expect(entry.size, isNull);
    });
  });

  group('BridgeProjectFilePreview', () {
    test('creates valid instance', () {
      final preview = BridgeProjectFilePreview(
        content: 'void main() {}',
        truncated: false,
        absPath: '/project/lib/main.dart',
      );
      expect(preview.content, 'void main() {}');
      expect(preview.truncated, false);
      expect(preview.error, isNull);
    });

    test('handles error case', () {
      final preview = BridgeProjectFilePreview(
        error: 'File not found',
        content: '',
        truncated: false,
        absPath: '/project/nonexistent.dart',
      );
      expect(preview.error, 'File not found');
      expect(preview.content, '');
    });
  });

  group('BridgeRootListResult', () {
    test('creates valid instance', () {
      final entries = [
        BridgeProjectListEntry(
          name: 'project1',
          type: 'dir',
          relPath: 'project1',
          absPath: '/home/user/project1',
        ),
      ];
      final result = BridgeRootListResult(
        root: '/home/user',
        path: '/home/user',
        entries: entries,
      );
      expect(result.root, '/home/user');
      expect(result.entries.length, 1);
      expect(result.error, isNull);
    });
  });

  group('ReminderListItem', () {
    test('creates valid instance', () {
      final reminder = ReminderListItem(
        id: 'rem_123',
        type: 'cron',
        message: 'Take medicine',
        schedule: '0 9 * * *',
        nextRun: '2026-04-21T09:00:00Z',
        enabled: true,
        friendId: 'friend_456',
      );
      expect(reminder.id, 'rem_123');
      expect(reminder.type, 'cron');
      expect(reminder.message, 'Take medicine');
      expect(reminder.schedule, '0 9 * * *');
      expect(reminder.enabled, true);
    });

    test('oneshot type', () {
      final reminder = ReminderListItem(
        id: 'rem_789',
        type: 'oneshot',
        message: 'Call mom',
        schedule: '2026-04-20T10:00:00Z',
        nextRun: '2026-04-20T10:00:00Z',
        enabled: false,
        friendId: 'friend_111',
      );
      expect(reminder.type, 'oneshot');
      expect(reminder.enabled, false);
    });
  });
}
