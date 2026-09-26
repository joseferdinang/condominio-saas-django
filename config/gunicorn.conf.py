import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
worker_class = "sync"
timeout = 90
graceful_timeout = 90
keepalive = 5
max_requests = 500
max_requests_jitter = 50
worker_tmp_dir = "/tmp"
accesslog = "-"
errorlog = "-"
capture_output = True
# Paths may contain password reset tokens. Do not log URLs, headers or bodies.
access_log_format = '%(t)s method=%(m)s status=%(s)s bytes=%(B)s duration_us=%(D)s'
# Only Caddy can reach this private container port; it overwrites this header.
forwarded_allow_ips = "*"
limit_request_line = 4094
limit_request_fields = 50
limit_request_field_size = 4094
