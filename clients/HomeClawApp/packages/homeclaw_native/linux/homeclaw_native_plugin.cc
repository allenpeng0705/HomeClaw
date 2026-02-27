#include "include/homeclaw_native/homeclaw_native_plugin.h"

#include <flutter_linux/flutter_linux.h>
#include <gtk/gtk.h>
#include <sys/utsname.h>
#include <cstring>
#include <glib/gstdio.h>

#include "homeclaw_native_plugin_private.h"

#define HOMECLAW_NATIVE_PLUGIN(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj), homeclaw_native_plugin_get_type(), \
                              HomeclawNativePlugin))

struct _HomeclawNativePlugin {
  GObject parent_instance;
};

G_DEFINE_TYPE(HomeclawNativePlugin, homeclaw_native_plugin, g_object_get_type())

// Called when a method call is received from Flutter.
static void homeclaw_native_plugin_handle_method_call(
    HomeclawNativePlugin* self,
    FlMethodCall* method_call) {
  g_autoptr(FlMethodResponse) response = nullptr;

  const gchar* method = fl_method_call_get_name(method_call);

  if (strcmp(method, "getPlatformVersion") == 0) {
    response = get_platform_version();
  } else if (strcmp(method, "showNotification") == 0) {
    FlValue* args = fl_method_call_get_args(method_call);
    if (args && fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      const gchar* title = "";
      const gchar* body = "";
      FlValue* title_val = fl_value_lookup_string(args, "title");
      if (title_val && fl_value_get_type(title_val) == FL_VALUE_TYPE_STRING)
        title = fl_value_get_string(title_val);
      FlValue* body_val = fl_value_lookup_string(args, "body");
      if (body_val && fl_value_get_type(body_val) == FL_VALUE_TYPE_STRING)
        body = fl_value_get_string(body_val);
      response = show_notification(title, body);
    } else {
      response = FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_null()));
    }
  } else if (strcmp(method, "getTraySupported") == 0) {
    response = FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_bool(TRUE)));
  } else if (strcmp(method, "setTrayIcon") == 0) {
    response = FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_null()));
  } else if (strcmp(method, "startScreenRecord") == 0) {
    FlValue* args = fl_method_call_get_args(method_call);
    int duration_sec = 10;
    gboolean include_audio = FALSE;
    if (args && fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* d = fl_value_lookup_string(args, "durationSec");
      if (d && fl_value_get_type(d) == FL_VALUE_TYPE_INT)
        duration_sec = fl_value_get_int(d);
      FlValue* a = fl_value_lookup_string(args, "includeAudio");
      if (a && fl_value_get_type(a) == FL_VALUE_TYPE_BOOL)
        include_audio = fl_value_get_bool(a);
    }
    response = start_screen_record(duration_sec, include_audio);
  } else {
    response = FL_METHOD_RESPONSE(fl_method_not_implemented_response_new());
  }

  fl_method_call_respond(method_call, response, nullptr);
}

FlMethodResponse* get_platform_version() {
  struct utsname uname_data = {};
  uname(&uname_data);
  g_autofree gchar *version = g_strdup_printf("Linux %s", uname_data.version);
  g_autoptr(FlValue) result = fl_value_new_string(version);
  return FL_METHOD_RESPONSE(fl_method_success_response_new(result));
}

FlMethodResponse* show_notification(const gchar* title, const gchar* body) {
  gchar* argv[4] = {
    g_strdup("notify-send"),
    g_strdup(title),
    g_strdup(body),
    nullptr
  };
  GError* err = nullptr;
  gint exit_status = 0;
  g_spawn_sync(nullptr, argv, nullptr, G_SPAWN_SEARCH_PATH,
               nullptr, nullptr, nullptr, nullptr, &err, &exit_status, nullptr);
  g_free(argv[0]);
  g_free(argv[1]);
  g_free(argv[2]);
  if (err) {
    g_error_free(err);
  }
  return FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_null()));
}

FlMethodResponse* start_screen_record(int duration_sec, gboolean include_audio) {
  (void)include_audio;
  g_autoptr(GError) err = nullptr;
  g_autofree gchar* tmpdir = g_dir_make_tmp("homeclaw_screen_XXXXXX", &err);
  if (!tmpdir) {
    return FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_null()));
  }
  g_autofree gchar* path = g_build_filename(tmpdir, "recording.mp4", nullptr);
  g_autofree gchar* duration_str = g_strdup_printf("%d", duration_sec);
  const char* display = g_getenv("DISPLAY");
  if (!display || !display[0]) display = ":0";
  gchar* argv[16];
  int i = 0;
  argv[i++] = g_strdup("ffmpeg");
  argv[i++] = g_strdup("-y");
  argv[i++] = g_strdup("-f");
  argv[i++] = g_strdup("x11grab");
  argv[i++] = g_strdup("-framerate");
  argv[i++] = g_strdup("15");
  argv[i++] = g_strdup("-t");
  argv[i++] = g_strdup(duration_str);
  argv[i++] = g_strdup("-i");
  argv[i++] = g_strdup(display);
  argv[i++] = g_strdup("-c:v");
  argv[i++] = g_strdup("libx264");
  argv[i++] = g_strdup("-preset");
  argv[i++] = g_strdup("ultrafast");
  argv[i++] = g_strdup(path);
  argv[i++] = nullptr;
  gint exit_status = 0;
  g_spawn_sync(nullptr, argv, nullptr, G_SPAWN_SEARCH_PATH,
              nullptr, nullptr, nullptr, &err, &exit_status, nullptr);
  for (int j = 0; j < i - 1; j++) g_free(argv[j]);
  if (err || exit_status != 0) {
    return FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_null()));
  }
  g_autofree gchar* abs_path = g_canonicalize_filename(path, nullptr);
  if (!abs_path || !g_file_test(abs_path, G_FILE_TEST_EXISTS)) {
    return FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_null()));
  }
  g_autoptr(FlValue) result = fl_value_new_string(abs_path);
  return FL_METHOD_RESPONSE(fl_method_success_response_new(result));
}

static void homeclaw_native_plugin_dispose(GObject* object) {
  G_OBJECT_CLASS(homeclaw_native_plugin_parent_class)->dispose(object);
}

static void homeclaw_native_plugin_class_init(HomeclawNativePluginClass* klass) {
  G_OBJECT_CLASS(klass)->dispose = homeclaw_native_plugin_dispose;
}

static void homeclaw_native_plugin_init(HomeclawNativePlugin* self) {}

static void method_call_cb(FlMethodChannel* channel, FlMethodCall* method_call,
                           gpointer user_data) {
  HomeclawNativePlugin* plugin = HOMECLAW_NATIVE_PLUGIN(user_data);
  homeclaw_native_plugin_handle_method_call(plugin, method_call);
}

void homeclaw_native_plugin_register_with_registrar(FlPluginRegistrar* registrar) {
  HomeclawNativePlugin* plugin = HOMECLAW_NATIVE_PLUGIN(
      g_object_new(homeclaw_native_plugin_get_type(), nullptr));

  g_autoptr(FlStandardMethodCodec) codec = fl_standard_method_codec_new();
  g_autoptr(FlMethodChannel) channel =
      fl_method_channel_new(fl_plugin_registrar_get_messenger(registrar),
                            "homeclaw_native",
                            FL_METHOD_CODEC(codec));
  fl_method_channel_set_method_call_handler(channel, method_call_cb,
                                            g_object_ref(plugin),
                                            g_object_unref);

  g_object_unref(plugin);
}
