"""Read-only HTTPS smoke test. Trust a local CA explicitly or use public trust."""
import argparse
import http.client
import json
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="e.g. https://localhost:18443")
    parser.add_argument("--ca-file")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    context = ssl.create_default_context(cafile=args.ca_file)

    def request(path, **kwargs):
        req = urllib.request.Request(base + path, **kwargs)
        try:
            return urllib.request.urlopen(req, context=context, timeout=15)
        except urllib.error.HTTPError as exc:
            return exc

    with request("/health/") as response:
        assert response.status == 200
        assert json.load(response) == {"status": "ok", "database": "ok"}
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "max-age=" in response.headers["Strict-Transport-Security"]
    with request("/cuentas/login/") as response:
        html = response.read().decode()
        assert response.status == 200
        cookies = response.headers.get_all("Set-Cookie") or []
        assert any("csrftoken=" in value and "Secure" in value and "SameSite=Lax" in value for value in cookies)
        resources = re.findall(r'(?:href|src)="(/static/[^\"]+)"', html)
        assert resources, "No se encontraron estáticos."
    for path in resources:
        with request(path) as response:
            assert response.status == 200, path
            assert len(response.read()) > 0
    with request("/media/privado.pdf") as response:
        assert response.status == 404
    with request("/cuentas/login/", data=b"username=probe&password=invalid") as response:
        assert response.status == 403, "CSRF debe rechazar POST sin token."
    # Declared body limit is enforced before form parsing.
    target = urlsplit(base)
    connection = http.client.HTTPSConnection(target.hostname, target.port, context=context, timeout=15)
    edge_rejected = False
    try:
        connection.putrequest("POST", "/cuentas/login/")
        connection.putheader("Content-Length", str(7 * 1024 * 1024))
        connection.endheaders()
        chunk = b"x" * (64 * 1024)
        for _ in range(112):
            connection.send(chunk)
        response = connection.getresponse()
        edge_rejected = response.status == 413
        response.close()
    except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError, OSError):
        # Caddy may terminate the upload as soon as it crosses the limit.
        edge_rejected = True
    finally:
        connection.close()
    assert edge_rejected, "El proxy aceptó una carga mayor de 6 MB."
    print("HTTPS validado: health/PostgreSQL, headers, cookie CSRF Secure, estáticos reales, media privado, CSRF y límite 413.")


if __name__ == "__main__":
    main()
