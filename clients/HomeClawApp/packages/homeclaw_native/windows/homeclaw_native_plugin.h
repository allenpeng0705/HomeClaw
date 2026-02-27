#ifndef FLUTTER_PLUGIN_HOMECLAW_NATIVE_PLUGIN_H_
#define FLUTTER_PLUGIN_HOMECLAW_NATIVE_PLUGIN_H_

#include <flutter/method_channel.h>
#include <flutter/plugin_registrar_windows.h>

#include <memory>

namespace homeclaw_native {

class HomeclawNativePlugin : public flutter::Plugin {
 public:
  static void RegisterWithRegistrar(flutter::PluginRegistrarWindows *registrar);

  HomeclawNativePlugin();

  virtual ~HomeclawNativePlugin();

  // Disallow copy and assign.
  HomeclawNativePlugin(const HomeclawNativePlugin&) = delete;
  HomeclawNativePlugin& operator=(const HomeclawNativePlugin&) = delete;

  // Called when a method is called on this plugin's channel from Dart.
  void HandleMethodCall(
      const flutter::MethodCall<flutter::EncodableValue> &method_call,
      std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result);
};

}  // namespace homeclaw_native

#endif  // FLUTTER_PLUGIN_HOMECLAW_NATIVE_PLUGIN_H_
