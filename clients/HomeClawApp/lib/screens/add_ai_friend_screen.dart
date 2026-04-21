import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../core_service.dart';
import '../providers/add_ai_friend_providers.dart';

/// Add AI Friend: create a custom AI friend (e.g. Sabrina, Gary) and persist to user.yml on Core.
/// Fields: name (required), relation (optional), identity text (optional), thumbnail (optional).
class AddAIFriendScreen extends ConsumerStatefulWidget {
  final CoreService coreService;

  const AddAIFriendScreen({super.key, required this.coreService});

  @override
  ConsumerState<AddAIFriendScreen> createState() => _AddAIFriendScreenState();
}

class _AddAIFriendScreenState extends ConsumerState<AddAIFriendScreen> {
  final _nameController = TextEditingController();
  final _relationController = TextEditingController();
  final _identityController = TextEditingController();
  late final AddAIFriendNotifier _notifier;

  @override
  void initState() {
    super.initState();
    _notifier = ref.read(addAIFriendProvider.notifier);
  }

  @override
  void dispose() {
    _nameController.dispose();
    _relationController.dispose();
    _identityController.dispose();
    super.dispose();
  }

  Future<void> _pickImage() async {
    try {
      final picker = ImagePicker();
      final x = await picker.pickImage(source: ImageSource.gallery, maxWidth: 512, imageQuality: 85);
      if (x != null && mounted) {
        final path = x.path;
        if (path.isNotEmpty) _notifier.setAvatar(File(path));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Pick image failed: $e')));
    }
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      _notifier.setError('Name is required');
      return;
    }
    if (name.toLowerCase() == 'homeclaw') {
      _notifier.setError('Cannot use the name HomeClaw');
      return;
    }
    _notifier.setSubmitting(true);
    try {
      await widget.coreService.addAIFriend(
        name: name,
        relation: _relationController.text.trim().isNotEmpty ? _relationController.text.trim() : null,
        identityText: _identityController.text.trim().isNotEmpty ? _identityController.text.trim() : null,
        avatarFile: ref.read(addAIFriendProvider).avatarFile,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('AI friend added')));
      Navigator.maybeOf(context)?.pop(true);
    } catch (e) {
      if (mounted) _notifier.setError(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(addAIFriendProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Add AI friend'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _nameController,
              decoration: const InputDecoration(
                labelText: 'Name *',
                hintText: 'e.g. Sabrina, Gary',
                border: OutlineInputBorder(),
              ),
              textCapitalization: TextCapitalization.words,
              onChanged: (_) => _notifier.clearError(),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _relationController,
              decoration: const InputDecoration(
                labelText: 'Relation (optional)',
                hintText: 'e.g. girlfriend, friend',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _identityController,
              decoration: const InputDecoration(
                labelText: 'Identity / persona (optional)',
                hintText: 'Describe who this AI friend is: tone, style, background…',
                alignLabelWithHint: true,
                border: OutlineInputBorder(),
              ),
              maxLines: 4,
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Text('Thumbnail (optional)', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: state.saving ? null : _pickImage,
                  icon: const Icon(Icons.photo_library_outlined, size: 20),
                  label: Text(state.avatarFile != null ? 'Change' : 'Pick image'),
                ),
              ],
            ),
            if (state.avatarFile != null) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.file(state.avatarFile!, height: 80, width: 80, fit: BoxFit.cover),
              ),
            ],
            if (state.error != null) ...[
              const SizedBox(height: 12),
              Text(state.error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: state.saving ? null : _submit,
              child: state.saving ? const SizedBox(height: 24, width: 24, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Add AI friend'),
            ),
          ],
        ),
      ),
    );
  }
}
