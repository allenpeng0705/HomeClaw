import 'package:flutter/material.dart';
import '../core_service.dart';
import '../widgets/homeclaw_snackbars.dart';

/// Form: send federated friend request (user id on peer Core + peers.yml instance_id).
class AddRemoteFriendPanel extends StatefulWidget {
  final CoreService coreService;

  const AddRemoteFriendPanel({super.key, required this.coreService});

  @override
  State<AddRemoteFriendPanel> createState() => _AddRemoteFriendPanelState();
}

class _AddRemoteFriendPanelState extends State<AddRemoteFriendPanel> {
  final _peerCtrl = TextEditingController();
  final _userCtrl = TextEditingController();
  final _msgCtrl = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _peerCtrl.dispose();
    _userCtrl.dispose();
    _msgCtrl.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final peer = _peerCtrl.text.trim();
    final uid = _userCtrl.text.trim();
    if (peer.isEmpty || uid.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Peer instance id and remote user id are required')),
      );
      return;
    }
    setState(() => _sending = true);
    try {
      await widget.coreService.sendFederatedFriendRequest(
        toUserId: uid,
        peerInstanceId: peer,
        message: _msgCtrl.text.trim().isEmpty ? null : _msgCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Request sent. They can accept under Friend requests → Remote.')),
      );
      _msgCtrl.clear();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(homeClawErrorSnackBar(context, '$e'));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Add someone on another HomeClaw Core. Use their user id on that server and the instance_id from your Core’s peers.yml.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _peerCtrl,
            decoration: const InputDecoration(
              labelText: 'Peer instance id',
              hintText: 'e.g. garage-core',
              border: OutlineInputBorder(),
            ),
            textInputAction: TextInputAction.next,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _userCtrl,
            decoration: const InputDecoration(
              labelText: 'Their user id (on their Core)',
              border: OutlineInputBorder(),
            ),
            textInputAction: TextInputAction.next,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _msgCtrl,
            decoration: const InputDecoration(
              labelText: 'Optional message',
              border: OutlineInputBorder(),
            ),
            maxLines: 2,
            textInputAction: TextInputAction.done,
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _sending ? null : _send,
            child: _sending
                ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Send remote request'),
          ),
        ],
      ),
    );
  }
}
