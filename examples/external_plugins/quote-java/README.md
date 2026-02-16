# Quote Plugin (Java)

External Quote plugin for HomeClaw, implemented in **Java** (JDK 11+, `com.sun.net.httpserver` + Gson).

- **Port:** 3113
- **Endpoints:** `GET /health`, `POST /run` (body = PluginRequest JSON, response = PluginResult JSON)

## Prerequisites

- JDK 11+
- Maven 3.x

## Run

```bash
cd examples/external_plugins/quote-java
mvn compile exec:java -Dexec.mainClass="QuotePlugin"
# Or: mvn package && java -cp "target/quote-plugin-1.0.0.jar:target/lib/*" QuotePlugin
```

## Register with Core

With Core running (default http://127.0.0.1:9000) and the plugin server running:

```bash
chmod +x register.sh
./register.sh
```

Then ask: "Give me an inspirational quote" or "Quote about success."
