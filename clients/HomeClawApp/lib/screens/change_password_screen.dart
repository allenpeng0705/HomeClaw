import 'package:flutter/material.dart';

import '../core_service.dart';

/// Screen to change the current user's password (Companion session).
/// Requires current password and new password (with confirmation).
class ChangePasswordScreen extends StatefulWidget {
  final CoreService coreService;

  const ChangePasswordScreen({super.key, required this.coreService});

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _currentController = TextEditingController();
  final _newController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _obscureCurrent = true;
  bool _obscureNew = true;
  bool _obscureConfirm = true;
  bool _submitting = false;

  @override
  void dispose() {
    _currentController.dispose();
    _newController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate() || _submitting) return;
    final current = _currentController.text.trim();
    final newPw = _newController.text;
    setState(() => _submitting = true);
    try {
      await widget.coreService.changePassword(oldPassword: current, newPassword: newPw);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Password changed')));
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Change password'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Form(
          key: _formKey,
          child: ListView(
            children: [
              TextFormField(
                controller: _currentController,
                decoration: InputDecoration(
                  labelText: 'Current password',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: Icon(_obscureCurrent ? Icons.visibility_off : Icons.visibility),
                    onPressed: () => setState(() => _obscureCurrent = !_obscureCurrent),
                  ),
                ),
                obscureText: _obscureCurrent,
                autocorrect: false,
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return 'Enter your current password';
                  return null;
                },
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _newController,
                decoration: InputDecoration(
                  labelText: 'New password',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: Icon(_obscureNew ? Icons.visibility_off : Icons.visibility),
                    onPressed: () => setState(() => _obscureNew = !_obscureNew),
                  ),
                ),
                obscureText: _obscureNew,
                autocorrect: false,
                validator: (v) {
                  if (v == null || v.isEmpty) return 'Enter a new password';
                  if (v.length > 512) return 'Password too long';
                  return null;
                },
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _confirmController,
                decoration: InputDecoration(
                  labelText: 'Confirm new password',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: Icon(_obscureConfirm ? Icons.visibility_off : Icons.visibility),
                    onPressed: () => setState(() => _obscureConfirm = !_obscureConfirm),
                  ),
                ),
                obscureText: _obscureConfirm,
                autocorrect: false,
                validator: (v) {
                  if (v == null || v.isEmpty) return 'Confirm your new password';
                  if (v != _newController.text) return 'Passwords do not match';
                  return null;
                },
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _submitting ? null : _submit,
                child: _submitting
                    ? const SizedBox(
                        height: 24,
                        width: 24,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Change password'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
