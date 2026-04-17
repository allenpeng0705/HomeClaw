// Companion UI helpers for dedicated preset chats: Reminder, Finder, Knowledge.
// Core: should_skip_intent_router_for_friend, config/friend_presets.yml.

/// Resolves [reminder] / [finder] / [knowledge] from API preset or friend display name.
String? resolveProductPresetKey({String? preset, String? friendName}) {
  final p = (preset ?? '').trim().toLowerCase();
  if (p == 'reminder' || p == 'finder' || p == 'knowledge') return p;
  final n = (friendName ?? '').trim();
  if (n.isEmpty) return null;
  final nl = n.toLowerCase();
  if (n == '知识库' ||
      nl == 'knowledge' ||
      nl == 'kb' ||
      nl == 'knowledgebase' ||
      nl == 'knowledge base') {
    return 'knowledge';
  }
  if (nl == 'reminder' || nl.contains('reminder')) return 'reminder';
  if (nl == 'finder' || nl == 'files' || nl.contains('finder')) return 'finder';
  return null;
}

typedef PresetQuickAction = ({String label, String text});

List<PresetQuickAction> presetQuickActionsFor(String key) {
  switch (key) {
    case 'reminder':
      return [
        (label: '30 min', text: 'Remind me in 30 minutes to '),
        (label: 'Tomorrow 9:00', text: 'Remind me tomorrow at 9:00 to '),
        (label: 'List reminders', text: 'List my upcoming reminders and recurring cron jobs'),
      ];
    case 'finder':
      return [
        (label: 'List documents', text: 'List files in my documents folder'),
        (label: 'Find file', text: 'Find files named '),
        (label: 'Summarize', text: 'Read and summarize the main points from '),
      ];
    case 'knowledge':
      return [
        (label: 'Search KB', text: 'Search my knowledge base for '),
        (label: 'List sources', text: 'List my knowledge base sources'),
        (label: 'Save note', text: 'Add this to my knowledge base: '),
      ];
    default:
      return const [];
  }
}

String? productPresetEmptyHint(String key) {
  switch (key) {
    case 'reminder':
      return 'Dedicated reminder chat — use the chips below or describe when to remind you.';
    case 'finder':
      return 'Files and documents — search, read, slides, and web search. Use chips or type a path or filename.';
    case 'knowledge':
      return 'Knowledge base — search saved materials and URLs. Use chips or ask in natural language.';
    default:
      return null;
  }
}
