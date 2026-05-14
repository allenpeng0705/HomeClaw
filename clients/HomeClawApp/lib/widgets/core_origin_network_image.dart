import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../core_service.dart';

/// [Image.network], or fetches through the Envoy tunnel when [coreService.coreHttpTunnelActive]
/// and [imageUrl] shares the same origin as Companion's Core URL (relay-only phones).
class CoreOriginNetworkImage extends StatelessWidget {
  final CoreService coreService;
  final String imageUrl;
  final double? width;
  final double? height;
  final BoxFit fit;
  final Map<String, String>? headers;
  final bool gaplessPlayback;
  final Widget Function(BuildContext, Widget child)? frameBuilder;
  final ImageLoadingBuilder? loadingBuilder;
  final Widget Function(BuildContext, Object error)? errorPlaceholder;

  const CoreOriginNetworkImage({
    super.key,
    required this.coreService,
    required this.imageUrl,
    this.width,
    this.height,
    this.fit = BoxFit.contain,
    this.headers,
    this.gaplessPlayback = true,
    this.frameBuilder,
    this.loadingBuilder,
    this.errorPlaceholder,
  });

  @override
  Widget build(BuildContext context) {
    final u = Uri.tryParse(imageUrl);
    final tunnel = u != null &&
        u.hasScheme &&
        coreService.coreHttpTunnelActive &&
        coreService.isSameCoreOriginAsCompanion(u);

    if (!tunnel) {
      return Image.network(
        imageUrl,
        width: width,
        height: height,
        fit: fit,
        headers: headers,
        gaplessPlayback: gaplessPlayback,
        loadingBuilder: loadingBuilder ?? _simpleLoadingFallback,
        errorBuilder: (_, __, ___) =>
            errorPlaceholder?.call(context, imageUrl) ??
            Icon(Icons.broken_image_outlined,
                color: Theme.of(context).colorScheme.outline, size: 40),
      );
    }

    return FutureBuilder<Uint8List?>(
      future: coreService.fetchTunnelRoutedCoreMediaBytes(u),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          final child = SizedBox.shrink();
          if (loadingBuilder != null) {
            return loadingBuilder!(
              context,
              SizedBox(width: width, height: height ?? 140, child: child),
              null,
            );
          }
          return SizedBox(
            width: width,
            height: height ?? 140,
            child: const Center(
              child: SizedBox(
                width: 28,
                height: 28,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          );
        }
        final bytes = snapshot.data;
        if (bytes == null || bytes.isEmpty) {
          return errorPlaceholder?.call(context, snapshot.error ?? 'empty') ??
              Icon(Icons.broken_image_outlined,
                  color: Theme.of(context).colorScheme.outline, size: 40);
        }
        final mem = Image.memory(
          bytes,
          width: width,
          height: height,
          fit: fit,
          gaplessPlayback: gaplessPlayback,
          errorBuilder: (_, __, ___) =>
              Icon(Icons.broken_image_outlined,
                  color: Theme.of(context).colorScheme.outline, size: 40),
        );
        if (frameBuilder != null) {
          return frameBuilder!(context, mem);
        }
        return mem;
      },
    );
  }

  Widget _simpleLoadingFallback(
    BuildContext context,
    Widget child,
    ImageChunkEvent? progress,
  ) {
    if (progress == null) return child;
    return SizedBox(
      width: width,
      height: height ?? 140,
      child: const Center(
        child: SizedBox(
          width: 28,
          height: 28,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      ),
    );
  }
}
