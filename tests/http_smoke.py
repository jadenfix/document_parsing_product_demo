"""Real local HTTP lifecycle check with explicit provider fixtures, not PDF accuracy."""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

ROOT = Path(__file__).resolve().parents[1]


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Expected when testing the application's short read timeout.

    def do_POST(self):
        if self.path != '/extraction_api':
            self.send_json(404, {'error': 'Unknown fixture route'})
            return
        body = self.rfile.read(int(self.headers['Content-Length']))
        match = re.search(rb'filename="([^"]+)"', body)
        if match is None or b'%PDF-' not in body:
            self.send_json(400, {'error': 'Expected uploaded PDF bytes'})
            return
        filename = match.group(1).decode()
        if filename == 'provider-failure.pdf':
            self.send_json(503, {'error': 'Explicit local provider unavailable fixture'})
            return
        if filename == 'provider-timeout.pdf':
            time.sleep(.8)
        self.send_json(200, [{'description': f'Fixture {filename} item {index}'}
                             for index in (1, 2)])

    def do_GET(self):
        from urllib.parse import parse_qs, urlsplit
        url = urlsplit(self.path)
        if url.path != '/match':
            self.send_json(404, {'error': 'Unknown fixture route'})
            return
        query = parse_qs(url.query)['query'][0]
        self.send_json(200, [{'match': f'Fixture catalogue {query} option {index}',
                             'score': .9 - index * .1} for index in (0, 1)])


class Choices(HTMLParser):
    def __init__(self):
        super().__init__()
        self.selections = {}
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'select':
            self.current = attrs.get('name')
            if self.current and self.current.isdigit():
                self.selections[self.current] = []
        if tag == 'option' and self.current in self.selections:
            value = attrs.get('value')
            if value is not None and value.isdigit():
                self.selections[self.current].append(value)

    def handle_endtag(self, tag):
        if tag == 'select':
            self.current = None


class Application:
    def __init__(self, folder, provider):
        self.folder = folder
        self.provider = provider
        self.process = None
        self.log = None

    def start(self):
        port_file = self.folder / 'port'
        port_file.unlink(missing_ok=True)
        env = dict(os.environ, DB_PATH=str(self.folder / 'data.sqlite'),
                   UPLOAD_FOLDER=str(self.folder / 'uploads'), SYNC_PARSE='0',
                   EXTRACT_ENDPOINT=self.provider + '/extraction_api',
                   MATCH_ENDPOINT=self.provider + '/match',
                   PROVIDER_CONNECT_TIMEOUT='1', PROVIDER_READ_TIMEOUT='.2',
                   SMOKE_PORT_FILE=str(port_file))
        code = ('import os; from app import app; from werkzeug.serving import make_server; '
                's=make_server("127.0.0.1",0,app,threaded=True); '
                'open(os.environ["SMOKE_PORT_FILE"],"w").write(str(s.server_port)); '
                's.serve_forever()')
        self.log = (self.folder / 'application.log').open('a')
        self.process = subprocess.Popen([sys.executable, '-u', '-c', code], cwd=ROOT,
                                        env=env, stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Flask process exited: ' +
                                   (self.folder / 'application.log').read_text()[-5000:])
            if port_file.exists() and port_file.read_text():
                self.url = 'http://127.0.0.1:' + port_file.read_text()
                try:
                    if requests.get(self.url, timeout=1).status_code == 200:
                        return
                except requests.RequestException:
                    pass
            time.sleep(.05)
        raise TimeoutError('Flask HTTP readiness timed out')

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log is not None:
            self.log.close()

    def upload(self, filename, content):
        response = requests.post(self.url + '/upload',
                                 files={'file': (filename, content, 'application/pdf')},
                                 allow_redirects=False, timeout=3)
        assert response.status_code == 302, (response.status_code, response.text)
        match = re.fullmatch(r'/review/(\d+)', response.headers['Location'])
        assert match, response.headers
        return int(match.group(1))

    def wait_status(self, document, expected):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            response = requests.get(f'{self.url}/status/{document}', timeout=2)
            assert response.status_code == 200, response.text
            result = response.json()
            assert result['id'] == document
            assert result['status'] in ('queued', 'processing', 'ready', 'failed')
            if result['status'] == expected:
                return result
            if result['status'] in ('ready', 'failed'):
                raise AssertionError(result)
            time.sleep(.03)
        raise TimeoutError(f'Document {document} did not become {expected}')


def pdf_fixture(text):
    """Build a tiny valid one-page PDF locally, without an extraction claim."""
    stream = f'BT /F1 12 Tf 50 750 Td ({text}) Tj ET'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
               b'/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' +
               stream + b'\nendstream']
    output = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f'{index} 0 obj\n'.encode() + value + b'\nendobj\n')
    start = len(output)
    output.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n'
                  f'startxref\n{start}\n%%EOF\n'.encode())
    return bytes(output)


def main():
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='parser-http-smoke-') as temporary:
            application = Application(Path(temporary),
                                      f'http://127.0.0.1:{provider.server_port}')
            try:
                application.start()
                documents = []
                match_ids = set()
                samples = []
                for index in (1, 2):
                    sample = Path(temporary) / f'fixture-order-{index}.pdf'
                    sample.write_bytes(pdf_fixture(f'Explicit local order fixture {index}'))
                    samples.append(sample)
                for sample in samples:
                    document = application.upload(sample.name, sample.read_bytes())
                    assert document not in [item[0] for item in documents]
                    application.wait_status(document, 'ready')
                    review = requests.get(f'{application.url}/review/{document}', timeout=3)
                    assert review.status_code == 200, review.text
                    parser = Choices()
                    parser.feed(review.text)
                    assert len(parser.selections) == 2, parser.selections
                    assert not match_ids.intersection(parser.selections)
                    match_ids.update(parser.selections)
                    assert all(options == ['0', '1'] for options in parser.selections.values())
                    selected = {name: '1' for name in parser.selections}
                    exported = requests.post(f'{application.url}/confirm/{document}',
                                             data=selected, timeout=3)
                    assert exported.status_code == 200, exported.text
                    rows = list(csv.DictReader(io.StringIO(exported.text)))
                    assert len(rows) == 2
                    expected = {f'Fixture {sample.name} item {index}' for index in (1, 2)}
                    assert {row['description'] for row in rows} == expected, rows
                    for row in rows:
                        assert row['confirmed_choice'] == (
                            'Fixture catalogue ' + row['description'] + ' option 1'), rows
                    documents.append((document, 'ready'))
                for filename, text in [('provider-failure.pdf', 'failed'),
                                       ('provider-timeout.pdf', 'timed out')]:
                    document = application.upload(filename, samples[0].read_bytes())
                    status = application.wait_status(document, 'failed')
                    assert text in status['error'].lower(), status
                    review = requests.get(f'{application.url}/review/{document}', timeout=3)
                    assert review.status_code == 502, review.text
                    assert status['error'] in review.text
                    assert '<select' not in review.text
                    exported = requests.post(f'{application.url}/confirm/{document}',
                                             data={}, timeout=3)
                    assert exported.status_code == 409, exported.text
                    documents.append((document, 'failed'))
                application.stop()
                application.start()
                for document, state in documents:
                    application.wait_status(document, state)
                print(json.dumps({'scope': 'real Flask HTTP with local provider fixtures; '
                                  'not live provider or PDF extraction quality',
                                  'uploaded_pdfs': len(documents), 'reviewed_and_exported': 2,
                                  'provider_503_failed_export_blocked': True,
                                  'provider_read_timeout_failed_export_blocked': True,
                                  'restart_status_persistence': True,
                                  'dynamic_document_and_match_ids': True}, indent=2))
            finally:
                application.stop()
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=2)


if __name__ == '__main__':
    main()
