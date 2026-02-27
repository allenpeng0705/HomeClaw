#include "include/homeclaw_native/homeclaw_native_plugin_c_api.h"

#include <flutter/plugin_registrar_windows.h>

#include "homeclaw_native_plugin.h"

void HomeclawNativePluginCApiRegisterWithRegistrar(
    FlutterDesktopPluginRegistrarRef registrar) {
  homeclaw_native::HomeclawNativePlugin::RegisterWithRegistrar(
      flutter::PluginRegistrarManager::GetInstance()
          ->GetRegistrar<flutter::PluginRegistrarWindows>(registrar));
}
