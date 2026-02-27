#include "homeclaw_native_plugin.h"

#include <windows.h>
#include <VersionHelpers.h>

#include <flutter/method_channel.h>
#include <flutter/plugin_registrar_windows.h>
#include <flutter/standard_method_codec.h>

#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace homeclaw_native {

namespace {

std::string GetStringFromMap(const flutter::EncodableMap& map, const char* key) {
  auto it = map.find(flutter::EncodableValue(key));
  if (it == map.end()) return {};
  const auto* s = std::get_if<std::string>(&it->second);
  return s ? *s : std::string();
}

// UTF-8 to UTF-16 for PowerShell
static std::wstring Utf8ToWide(const std::string& utf8) {
  if (utf8.empty()) return L"";
  int size = MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), -1, nullptr, 0);
  if (size <= 0) return L"";
  std::wstring out(size - 1, 0);
  MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), -1, &out[0], size);
  return out;
}

// Escape for PowerShell single-quoted string: ' -> ''
static std::wstring EscapeForPsSingleQuoted(const std::wstring& w) {
  std::wstring out;
  out.reserve(w.size() + 8);
  for (wchar_t c : w) {
    if (c == L'\'') out += L"''";
    else if (c == L'\n') out += L" ";
    else if (c != L'\r') out += c;
  }
  return out;
}

// Show Windows 10+ Toast via PowerShell (no C++/WinRT dependency).
void ShowToast(const std::string& title_utf8, const std::string& body_utf8) {
  std::wstring title_w = EscapeForPsSingleQuoted(Utf8ToWide(title_utf8));
  std::wstring body_w = EscapeForPsSingleQuoted(Utf8ToWide(body_utf8));
  std::wstring script = L"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
    L"$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
    L"$t.GetElementsByTagName('text').Item(0).InnerText = '" + title_w + L"'; "
    L"$t.GetElementsByTagName('text').Item(1).InnerText = '" + body_w + L"'; "
    L"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('HomeClaw').Show([Windows.UI.Notifications.ToastNotification]::new($t))";
  std::wstring cmd = L"powershell.exe -NoProfile -WindowStyle Hidden -Command \"& { " + script + L" }\"";

  std::vector<wchar_t> cmd_buf(cmd.begin(), cmd.end());
  cmd_buf.push_back(L'\0');

  STARTUPINFOW si = {};
  si.cb = sizeof(si);
  si.dwFlags = STARTF_USESHOWWINDOW;
  si.wShowWindow = SW_HIDE;
  PROCESS_INFORMATION pi = {};
  if (CreateProcessW(nullptr, cmd_buf.data(), nullptr, nullptr, FALSE,
                     CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
  }
}

}  // namespace

// static
void HomeclawNativePlugin::RegisterWithRegistrar(
    flutter::PluginRegistrarWindows *registrar) {
  auto channel =
      std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
          registrar->messenger(), "homeclaw_native",
          &flutter::StandardMethodCodec::GetInstance());

  auto plugin = std::make_unique<HomeclawNativePlugin>();

  channel->SetMethodCallHandler(
      [plugin_pointer = plugin.get()](const auto &call, auto result) {
        plugin_pointer->HandleMethodCall(call, std::move(result));
      });

  registrar->AddPlugin(std::move(plugin));
}

HomeclawNativePlugin::HomeclawNativePlugin() {}

HomeclawNativePlugin::~HomeclawNativePlugin() {}

void HomeclawNativePlugin::HandleMethodCall(
    const flutter::MethodCall<flutter::EncodableValue> &method_call,
    std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
  const auto& method = method_call.method_name();

  if (method.compare("getPlatformVersion") == 0) {
    std::ostringstream version_stream;
    version_stream << "Windows ";
    if (IsWindows10OrGreater()) {
      version_stream << "10+";
    } else if (IsWindows8OrGreater()) {
      version_stream << "8";
    } else if (IsWindows7OrGreater()) {
      version_stream << "7";
    }
    result->Success(flutter::EncodableValue(version_stream.str()));
    return;
  }

  if (method.compare("showNotification") == 0) {
    const auto* args = method_call.arguments()
        ? std::get_if<flutter::EncodableMap>(method_call.arguments())
        : nullptr;
    if (!args) {
      result->Success(flutter::EncodableValue());
      return;
    }
    std::string title = GetStringFromMap(*args, "title");
    std::string body = GetStringFromMap(*args, "body");
    if (IsWindows10OrGreater()) {
      ShowToast(title, body);
    }
    result->Success(flutter::EncodableValue());
    return;
  }

  if (method.compare("getTraySupported") == 0) {
    result->Success(flutter::EncodableValue(true));
    return;
  }

  if (method.compare("setTrayIcon") == 0) {
    result->Success(flutter::EncodableValue());
    return;
  }

  if (method.compare("startScreenRecord") == 0) {
    result->Success(flutter::EncodableValue());
    return;
  }

  result->NotImplemented();
}

}  // namespace homeclaw_native
