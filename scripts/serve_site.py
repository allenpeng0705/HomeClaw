#!/usr/bin/env python3
"""
Serve the site/ folder (static files for promoting HomeClaw).
Works on Windows and Linux. Used by systemd (Linux) or NSSM / Task Scheduler (Windows).
Usage: python scripts/serve_site.py [port]
       Or: set PORT=3000 && python scripts/serve_site.py
Default port: 9999.
"""
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.environ.get("HOMECLAW_REPO_ROOT") or os.path.dirname(script_dir)
    site_dir = os.path.join(repo_root, "site")
    if not os.path.isdir(site_dir):
        print(f"Error: site directory not found at {site_dir}", file=sys.stderr)
        sys.exit(1)
    port = int(os.environ.get("PORT", "9999"))
    if len(sys.argv) >= 2:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    os.chdir(site_dir)
    server = HTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    print(f"Serving site at http://127.0.0.1:{port} (directory: {site_dir})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()

if __name__ == "__main__":
    main()
