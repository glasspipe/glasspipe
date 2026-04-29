import http.server
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
http.server.HTTPServer(('', 8000), http.server.SimpleHTTPRequestHandler).serve_forever()
