import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../core_service.dart';

/// Add AI Friend: create a custom AI friend (e.g. Sabrina, Gary) and persist to user.yml on Core.
/// Fields: name (required), relation (optional), identity text (optional), thumbnail (optional).
class AddAIFriendScreen extends StatefulWidget {
  final CoreService coreService;

  const AddAIFriendScreen({super.key, required this.coreService});

  @override
  State<AddAIFriendScreen> createState() => _AddAIFriendScreenState();
}

class _AddAIFriendScreenState extends State<AddAIFriendScreen> {
  final _nameController = TextEditingController();
  final _relationController = TextEditingController();
  final _identityController = TextEditingController();
  File? _avatarFile;
  bool _saving = false;
  String? _error;

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
        if (path.isNotEmpty) setState(() => _avatarFile = File(path));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Pick image failed: $e')));
    }
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Name is required');
      return;
    }
    if (name.toLowerCase() == 'homeclaw') {
      setState(() => _error = 'Cannot use the name HomeClaw');
      return;
    }
    setState(() {
      _error = null;
      _saving = true;
    });
    try {
      await widget.coreService.addAIFriend(
        name: name,
        relation: _relationController.text.trim().isNotEmpty ? _relationController.text.trim() : null,
        identityText: _identityController.text.trim().isNotEmpty ? _identityController.text.trim() : null,
        avatarFile: _avatarFile,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('AI friend added')));
      Navigator.maybeOf(context)?.pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
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
              onChanged: (_) => setState(() => _error = null),
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
                  onPressed: _saving ? null : _pickImage,
                  icon: const Icon(Icons.photo_library_outlined, size: 20),
                  label: Text(_avatarFile != null ? 'Change' : 'Pick image'),
                ),
              ],
            ),
            if (_avatarFile != null) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.file(_avatarFile!, height: 80, width: 80, fit: BoxFit.cover),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _saving ? null : _submit,
              child: _saving ? const SizedBox(height: 24, width: 24, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Add AI friend'),
            ),
          ],
        ),
      ),
    );
  }
}
