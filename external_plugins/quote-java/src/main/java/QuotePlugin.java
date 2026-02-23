/**
 * External Quote Plugin - Java HTTP server (com.sun.net.httpserver + Gson).
 * Run: mvn compile exec:java -Dexec.mainClass="QuotePlugin"
 * Or: mvn package && java -jar target/quote-plugin-1.0.0.jar
 * Register with Core: see README (curl or register.sh)
 *
 * Contract: GET /health (2xx), POST /run body=PluginRequest JSON, response=PluginResult JSON.
 */

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class QuotePlugin {

    private static final int PORT = 3113;
    private static final Gson gson = new Gson();

    private static final String[][] QUOTES = {
        {"The only way to do great work is to love what you do.", "Steve Jobs", "motivation"},
        {"Innovation distinguishes between a leader and a follower.", "Steve Jobs", "innovation"},
        {"Stay hungry, stay foolish.", "Steve Jobs", "motivation"},
        {"The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt", "dreams"},
        {"Success is not final, failure is not fatal.", "Winston Churchill", "success"},
        {"The only impossible journey is the one you never begin.", "Tony Robbins", "motivation"},
    };

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", PORT), 0);

        server.createContext("/health", exchange -> {
            if ("GET".equals(exchange.getRequestMethod())) {
                sendJson(exchange, 200, "{\"status\":\"ok\"}");
            } else {
                exchange.sendResponseHeaders(405, -1);
            }
        });

        server.createContext("/run", exchange -> {
            if (!"POST".equals(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, -1);
                return;
            }
            try {
                String body = readBody(exchange.getRequestBody());
                JsonObject data = gson.fromJson(body, JsonObject.class);
                String requestId = getStr(data, "request_id");
                String pluginId = getStr(data, "plugin_id");
                if (pluginId == null || pluginId.isEmpty()) pluginId = "quote";
                String capId = getStr(data, "capability_id");
                if (capId == null || capId.isEmpty()) capId = "get_quote";
                capId = capId.trim().toLowerCase().replace(" ", "_");

                JsonObject params = data.has("capability_parameters") && data.get("capability_parameters").isJsonObject()
                    ? data.getAsJsonObject("capability_parameters") : new JsonObject();
                String topic = getStr(params, "topic");
                if (topic != null) topic = topic.trim();
                String style = getStr(params, "style");
                if (style != null) style = style.trim();

                String text;
                if ("get_quote_by_topic".equals(capId)) {
                    text = getRandomQuote(topic, style);
                } else {
                    text = getRandomQuote(null, style);
                }

                Map<String, Object> result = new LinkedHashMap<>();
                result.put("request_id", requestId != null ? requestId : "");
                result.put("plugin_id", pluginId);
                result.put("success", true);
                result.put("text", text);
                result.put("error", (Object) null);
                result.put("metadata", Collections.emptyMap());
                sendJson(exchange, 200, gson.toJson(result));
            } catch (Exception e) {
                Map<String, Object> err = new LinkedHashMap<>();
                err.put("request_id", "");
                err.put("plugin_id", "quote");
                err.put("success", false);
                err.put("text", "");
                err.put("error", e.getMessage());
                err.put("metadata", Collections.emptyMap());
                sendJson(exchange, 500, gson.toJson(err));
            }
        });

        server.setExecutor(null);
        server.start();
        System.out.println("Quote plugin (Java) listening on http://0.0.0.0:" + PORT);
    }

    private static String getRandomQuote(String topic, String style) {
        List<String[]> pool = new ArrayList<>();
        if (topic != null && !topic.isEmpty()) {
            String t = topic.toLowerCase();
            for (String[] q : QUOTES) {
                if (q[2] != null && q[2].toLowerCase().contains(t)) pool.add(q);
            }
        }
        if (pool.isEmpty()) pool.addAll(Arrays.asList(QUOTES));
        String[] q = pool.get(new Random().nextInt(pool.size()));
        String quote = q[0], author = q[1];
        if (style != null && "short".equalsIgnoreCase(style)) {
            return "\"" + quote + "\" — " + author;
        }
        return "Quote: \"" + quote + "\"\nAuthor: " + author;
    }

    private static String readBody(InputStream in) throws IOException {
        StringBuilder sb = new StringBuilder();
        try (Reader r = new InputStreamReader(in, StandardCharsets.UTF_8)) {
            char[] buf = new char[4096];
            int n;
            while ((n = r.read(buf)) != -1) sb.append(buf, 0, n);
        }
        return sb.toString();
    }

    private static String getStr(JsonObject o, String key) {
        if (o == null || !o.has(key)) return null;
        return o.get(key).isJsonNull() ? null : o.get(key).getAsString();
    }

    private static void sendJson(HttpExchange exchange, int code, String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }
}
