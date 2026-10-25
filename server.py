"""Local-only PCB Flow Studio bridge. Python 3.10+, standard library only.

The browser performs constrained placement/routing and internal checks.
This server optionally invokes an actual KiCad CLI on isolated generated files.
It never accepts a source board path and never writes the user's existing PCB.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
import webbrowser

ROOT = Path(__file__).resolve().parent
MAX_BODY = 16 * 1024 * 1024


def discover_kicad(explicit: str | None = None) -> str | None:
    candidates = [explicit, os.environ.get('KICAD_CLI'), shutil.which('kicad-cli')]
    if os.name == 'nt':
        for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),):
            folder = Path(base) / 'KiCad'
            if folder.exists():
                candidates.extend(str(p / 'bin' / 'kicad-cli.exe') for p in sorted(folder.iterdir(), reverse=True))
    for value in candidates:
        if value and Path(value).is_file():
            return str(Path(value).resolve())
    return None


def cli_version(cli: str | None) -> str | None:
    """Read KiCad's documented version subcommand; support older flag-based CLIs."""
    if not cli:
        return None
    for arg in ('version', '--version'):
        try:
            p = subprocess.run([cli, arg], capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    return None


def new_run(output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    p = output_root / ('flow_' + tag)
    p.mkdir(exist_ok=False)
    return p


def prepare_library(folder: Path) -> None:
    """Copy only bundled demo footprints; never use paths supplied in a request."""
    source = ROOT / 'examples' / 'PCBFlow.pretty'
    if source.is_dir():
        shutil.copytree(source, folder / 'PCBFlow.pretty')
        (folder / 'fp-lib-table').write_text('(fp_lib_table (lib (name "PCBFlow")(type "KiCad")(uri "${KIPRJMOD}/PCBFlow.pretty")(options "")(descr "PCB Flow self-contained demo footprints")))\n', encoding='utf-8')


def parse_drc(report: dict, version: str, pcb_sha: str, returncode: int, stdout: str, stderr: str) -> dict:
    """No success status is inferred from exit code alone. Preserve raw violations."""
    if not isinstance(report, dict) or not isinstance(report.get('violations'), list) or not isinstance(report.get('unconnected_items'), list):
        raise ValueError('KiCad JSON report is missing violations/unconnected_items; no pass status can be established.')
    violations = report['violations']
    unconnected = report['unconnected_items']
    parity = report.get('schematic_parity', [])
    errors = sum(v.get('severity', 'error') == 'error' for v in violations)
    warnings = sum(v.get('severity') == 'warning' for v in violations)
    other = sum(v.get('severity', 'error') not in ('error', 'warning') for v in violations)
    return {'status': 'completed', 'version': version,
            'passed': returncode == 0 and len(violations) == 0 and len(unconnected) == 0 and len(parity) == 0,
            'errors': errors, 'warnings': warnings, 'other_violations': other,
            'unconnected': len(unconnected), 'schematic_parity_items': len(parity),
            'pcb_sha256': pcb_sha, 'returncode': returncode,
            'stdout': stdout, 'stderr': stderr, 'raw_report': report,
            'created': datetime.now(timezone.utc).isoformat(),
            'scope': 'Native KiCad PCB DRC under the recorded project and .kicad_dru rules; not ERC, circuit simulation or manufacturing approval.'}


def run_drc(cli: str, version: str, output_root: Path, payload: dict) -> dict:
    pcb = payload.get('pcb')
    project = payload.get('project', '{}')
    rules = payload.get('rules', '(version 1)\n')
    if not isinstance(pcb, str) or not pcb.lstrip().startswith('(kicad_pcb'):
        raise ValueError('Expected a generated KiCad PCB string, not a filesystem path.')
    if not isinstance(project, str) or not isinstance(json.loads(project), dict):
        raise ValueError('Project settings must be a JSON object.')
    if not isinstance(rules, str) or not rules.lstrip().startswith('(version 1)'):
        raise ValueError('Invalid rules file.')
    folder = new_run(output_root)
    (folder / 'afe.kicad_pcb').write_bytes(pcb.encode('utf-8'))
    (folder / 'afe.kicad_pro').write_bytes(project.encode('utf-8'))
    (folder / 'afe.kicad_dru').write_bytes(rules.encode('utf-8'))
    prepare_library(folder)
    sha = hashlib.sha256(pcb.encode('utf-8')).hexdigest()
    cmd = [cli, 'pcb', 'drc', '--format', 'json', '--all-track-errors', '--severity-all', '--output', 'native_drc.json', 'afe.kicad_pcb']
    p = subprocess.run(cmd, cwd=folder, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=150)
    (folder / 'cli_stdout.txt').write_text(p.stdout, encoding='utf-8')
    (folder / 'cli_stderr.txt').write_text(p.stderr, encoding='utf-8')
    report_path = folder / 'native_drc.json'
    if not report_path.exists():
        raise RuntimeError(f'KiCad did not create a DRC report (exit {p.returncode}): {(p.stderr or p.stdout)[-3000:]}')
    if hashlib.sha256((folder / 'afe.kicad_pcb').read_bytes()).hexdigest() != sha:
        raise RuntimeError('KiCad modified the generated PCB. The report cannot be associated with the browser result.')
    result = parse_drc(json.loads(report_path.read_text(encoding='utf-8-sig')), version, sha, p.returncode, p.stdout, p.stderr)
    result.update({'output_folder': str(folder), 'command': cmd,
                   'project_sha256': hashlib.sha256(project.encode()).hexdigest(),
                   'rules_sha256': hashlib.sha256(rules.encode()).hexdigest()})
    (folder / 'native_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def export_netlist(cli: str, output_root: Path, payload: dict) -> dict:
    text = payload.get('schematic')
    if not isinstance(text, str) or not text.lstrip().startswith('(kicad_sch'):
        raise ValueError('Expected KiCad schematic text.')
    if '(sheet ' in text or '(sheet\n' in text:
        raise ValueError('Hierarchical projects need their referenced sheet files. Export a KiCad XML netlist from the complete project, then import the .net file.')
    folder = new_run(output_root)
    (folder / 'afe.kicad_sch').write_text(text, encoding='utf-8')
    p = subprocess.run([cli, 'sch', 'export', 'netlist', '--format', 'kicadxml', '--output', 'afe.net', 'afe.kicad_sch'], cwd=folder, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    path = folder / 'afe.net'
    if p.returncode != 0 or not path.exists():
        raise RuntimeError(f'KiCad schematic netlist export failed: {(p.stderr or p.stdout)[-3000:]}')
    return {'netlist': path.read_text(encoding='utf-8-sig'), 'source_sha256': hashlib.sha256(text.encode()).hexdigest(), 'output_folder': str(folder)}


class FlowServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, host: str, port: int, cli: str | None, output: Path):
        super().__init__((host, port), Handler)
        self.cli = cli
        self.version = cli_version(cli)
        self.output_root = output
        self.cli_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server: FlowServer
    def json_response(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self) -> bool:
        # Resist cross-origin POSTs and DNS rebinding to a local service.
        host = self.headers.get('Host', '')
        port = self.server.server_address[1]
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if host not in allowed:
            return False
        origin = self.headers.get('Origin')
        return origin is None or origin in {f'http://{h}' for h in allowed}

    def do_GET(self) -> None:
        if not self.valid_host():
            self.json_response({'error': 'Untrusted Host / Origin.'}, 403)
            return
        path = urlparse(self.path).path
        if path == '/api/capabilities':
            self.json_response({'version': '2.0.0-flow', 'kicad_available': bool(self.server.version), 'kicad_version': self.server.version, 'native_drc_is_simulated': False})
            return
        if path == '/':
            filename = ROOT / 'OPEN_DEMO.html'
        else:
            rel = unquote(path).lstrip('/')
            filename = (ROOT / 'app' / rel).resolve()
            if not filename.is_relative_to((ROOT / 'app').resolve()):
                self.json_response({'error': 'Invalid static path.'}, 403)
                return
        if not filename.is_file() or filename.suffix not in {'.html', '.js', '.css'}:
            self.json_response({'error': 'Not found.'}, 404)
            return
        data = filename.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css'}[filename.suffix] + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if not self.valid_host():
            self.json_response({'error': 'Untrusted Host / Origin.'}, 403)
            return
        endpoint = urlparse(self.path).path
        if endpoint not in {'/api/drc', '/api/schematic'}:
            self.json_response({'error': 'Not found.'}, 404)
            return
        if not self.server.cli or not self.server.version:
            self.json_response({'error': 'KiCad CLI not found or could not report a version. No native check was run.'}, 503)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_BODY:
                self.json_response({'error': 'Invalid request size.'}, 413)
                return
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('Expected JSON object.')
            if not self.server.cli_lock.acquire(blocking=False):
                self.json_response({'error': 'Another KiCad operation is running. Try again after it finishes.'}, 409)
                return
            try:
                if endpoint == '/api/drc':
                    result = run_drc(self.server.cli, self.server.version, self.server.output_root, payload)
                else:
                    result = export_netlist(self.server.cli, self.server.output_root, payload)
            finally:
                self.server.cli_lock.release()
            self.json_response(result)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
            self.json_response({'error': str(e)}, 400)
        except subprocess.TimeoutExpired:
            self.json_response({'error': 'KiCad operation timed out; no successful check is claimed.'}, 504)
        except (OSError, RuntimeError) as e:
            self.json_response({'error': str(e)}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--kicad-cli', help='Explicit path to a KiCad CLI binary.')
    parser.add_argument('--outputs', type=Path, default=ROOT / 'runs')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('--port must be between 1024 and 65535')
    cli = discover_kicad(args.kicad_cli)
    try:
        server = FlowServer('127.0.0.1', args.port, cli, args.outputs.resolve())
    except OSError as e:
        parser.exit(1, f'Cannot start local server: {e}\nChoose another --port or close the previous process.\n')
    url = f'http://127.0.0.1:{args.port}/'
    print(f'PCB Agent Flow Studio\n{url}\nKiCad: {server.version or "not detected; internal browser checker remains available"}\nOutputs: {args.outputs.resolve()}\nCtrl+C to stop.', flush=True)
    if not args.no_browser:
        threading.Timer(.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
