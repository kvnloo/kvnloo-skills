#!/usr/bin/env python3
"""Offline, reversible skill links. Python 3.11+ standard library only."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

HARNESS_NAMES = ('claude', 'codex', 'hermes-clean', 'hermes-chiefstaff', 'agents')
NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')


def exists(path):
    return os.path.lexists(path)


def matches(path, target):
    return path.is_symlink() and os.readlink(path) == str(target)


def expand(path, home):
    if path == '~':
        return home
    if path.startswith('~/'):
        return home / path[2:]
    if '~' in path or '$' in path:
        raise ValueError('Paths support ~/ only; shell expansion is disabled')
    return Path(path).absolute()


def move(src, dst):
    """Rename. Across filesystems, retire the source only after a complete copy."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dst)
        return
    except OSError as error:
        # Any other failure (for example a read-only directory) changed nothing.
        if error.errno != errno.EXDEV:
            raise
    folder = src.is_dir() and not src.is_symlink()
    locked = [src.parent] + ([Path(d) for d, _, _ in os.walk(src)] if folder else [])
    for directory in locked:
        if not os.access(directory, os.W_OK | os.X_OK):
            raise PermissionError(f'Cannot move out of read-only directory: {directory}')
    partial = dst.with_name(dst.name + '.partial')
    if exists(partial):
        raise ValueError(f'Incomplete earlier copy; inspect it and move it away: {partial}')
    if src.is_symlink():
        os.symlink(os.readlink(src), partial)
    elif folder:
        shutil.copytree(src, partial, symlinks=True)
    else:
        shutil.copy2(src, partial)
    os.rename(partial, dst)
    if folder:
        shutil.rmtree(src)
    else:
        src.unlink()


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    os.replace(temporary, path)


class Installer:
    def __init__(self, args):
        self.args = args
        self.home = Path(args.home or os.environ.get('HOME', str(Path.home()))).absolute()
        self.manifest = Path(args.manifest).absolute()
        self.root = self.manifest.parent
        self.config = tomllib.loads(self.manifest.read_text())
        if self.config.get('schema_version') != 1:
            raise ValueError('Unsupported manifest schema_version')
        self.harnesses = self.config['harnesses']
        if set(self.harnesses) != set(HARNESS_NAMES):
            raise ValueError('Manifest must declare the five supported harnesses')
        self.directories = {h: expand(v['directory'], self.home)
                            for h, v in self.harnesses.items()}
        # Explicit --home isolates fake homes from inherited host overrides.
        if args.home is None:
            if os.environ.get('CLAUDE_CONFIG_DIR'):
                self.directories['claude'] = expand(os.environ['CLAUDE_CONFIG_DIR'], self.home) / 'skills'
            if os.environ.get('HERMES_HOME'):
                # Inside a profile HERMES_HOME is <root>/profiles/<profile>.
                hermes = expand(os.environ['HERMES_HOME'], self.home)
                if hermes.parent.name == 'profiles':
                    hermes = hermes.parent.parent
                for h in ('hermes-clean', 'hermes-chiefstaff'):
                    self.directories[h] = hermes / 'profiles' / h[7:] / 'skills'
        self.selected = [args.harness] if args.harness else list(HARNESS_NAMES)
        self.state_dir = self.home / '.local/state/kvnloo-skills'
        self.state_path = self.state_dir / 'links.json'
        self.reload()
        self.sources = {}

    def reload(self):
        self.state = read_json(self.state_path, {'version': 1, 'links': {}})
        if self.state.get('version') != 1:
            raise ValueError('Unsupported installer state version')

    @contextmanager
    def locked(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.state_dir / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.reload()
            yield

    def source(self, value):
        if value.startswith('local:'):
            return expand(value[6:], self.home).resolve()
        if value.startswith('git:'):
            key, relative = value[4:].split(':', 1)
            spec = self.config.get('sources', {})[key]
            commit = spec['commit']
            if not re.fullmatch('[0-9a-f]{40}', commit):
                raise ValueError(f'Invalid commit pin for {key}')
            if key not in self.sources:
                checkout = expand(spec['checkout'], self.home)
                if not checkout.is_dir():
                    raise FileNotFoundError(f'pinned checkout missing: {checkout}')
                head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'],
                                      capture_output=True, text=True)
                dirty = subprocess.run(['git', '-C', str(checkout), 'status', '--porcelain', '--untracked-files=all'],
                                       capture_output=True, text=True)
                if head.returncode or head.stdout.strip() != commit or dirty.returncode or dirty.stdout:
                    raise ValueError(f'checkout {key} must be clean at {commit}')
                self.sources[key] = checkout.resolve()
            path = (self.sources[key] / relative).resolve()
            if not path.is_relative_to(self.sources[key]):
                raise ValueError('Source path escapes checkout')
            return path
        path = (self.root / value).resolve()
        if Path(value).is_absolute() or not path.is_relative_to(self.root.resolve()):
            raise ValueError('In-repo sources must remain inside the repository')
        return path

    def skills(self):
        items = dict(self.config.get('skills', {}))
        if self.args.private:
            overlay = self.home / '.local/share/kvnloo-skills-private/skills'
            if overlay.is_dir():
                for path in sorted(overlay.iterdir()):
                    if (path / 'SKILL.md').is_file():
                        if path.name in items:
                            raise ValueError(f'Private overlay name collides with manifest: {path.name}')
                        items[path.name] = {'source': 'local:' + str(path),
                                            'harnesses': list(HARNESS_NAMES), 'pack': 'default'}
        packs = {'default', *self.args.pack}
        known = {s['pack'] for s in items.values()} | {'default'}
        if not packs <= known:
            raise ValueError('Unknown pack: ' + ', '.join(sorted(packs - known)))
        for name, spec in items.items():
            if not NAME.fullmatch(name) or len(name) > 64:
                raise ValueError(f'Invalid skill name: {name}')
            if not set(spec['harnesses']) <= set(HARNESS_NAMES):
                raise ValueError(f'Unknown harness for {name}')
            if spec['pack'] in packs:
                yield name, spec

    def destination(self, harness, name):
        directory = self.directories[harness]
        # Hermes already discovers categorized skills. Keep the existing path
        # and name to avoid duplicates and to preserve its telemetry key.
        if harness.startswith('hermes-') and directory.is_dir():
            found = []
            for parent, dirs, files in os.walk(directory, followlinks=False):
                if 'SKILL.md' in files:
                    dirs[:] = []  # never look inside a skill's own folders
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for child in dirs:
                    candidate = Path(parent) / child
                    if child == name and (candidate.is_symlink() or (candidate / 'SKILL.md').is_file()):
                        found.append(candidate)
            if len(found) > 1:
                raise ValueError(f'Multiple Hermes paths for {name}; resolve them before applying')
            if found:
                return found[0].parent.resolve() / name
        return directory.resolve() / name

    def plan(self):
        operations = {}
        # A harness that is not installed is skipped; its directories are never invented.
        active = []
        for h in self.selected:
            if self.directories[h].parent.is_dir():
                active.append(h)
            else:
                print(f'SKIP [{h}] harness directory missing: {self.directories[h].parent}')
        totals = {h: {'links': 0, 'folders': 0, 'symlinks': 0, 'files': 0} for h in active}
        sources = set()
        for name, spec in self.skills():
            relevant = [h for h in active if h in spec['harnesses']]
            if not relevant:
                continue
            try:
                source = self.source(spec['source'])
                if not (source / 'SKILL.md').is_file():
                    raise FileNotFoundError(f'SKILL.md missing: {source}')
            except (FileNotFoundError, ValueError) as error:
                print(f'UNAVAILABLE {name}: {error}')
                continue
            sources.add(source)
            for h in relevant:
                # Respect the Hermes curator: an archived skill stays archived.
                if h.startswith('hermes-') and exists(self.directories[h] / '.archive' / name):
                    print(f'ARCHIVED [{h}] {name}: left archived')
                    continue
                dest = self.destination(h, name)
                if dest == source or (exists(dest) and dest.resolve() == source):
                    print(f'KEEP [{h}] {dest}')
                    continue
                record = self.state['links'].get(str(dest))
                if record and (record['target'] != str(source) or
                               (exists(dest) and not matches(dest, source) and
                                record.get('phase') != 'prepared')):
                    raise ValueError(f'Managed path changed: {dest}; restore or uninstall first')
                kind = None
                if exists(dest):
                    kind = 'symlink' if dest.is_symlink() else 'folder' if dest.is_dir() else 'file'
                    print(f'MOVE [{h}] {dest} -> {self.state_dir}/backup-<date>/originals/<id> ({kind})')
                    totals[h][kind + 's'] += 1
                print(f'LINK [{h}] {dest} -> {source}')
                totals[h]['links'] += 1
                if str(dest) in operations:
                    if operations[str(dest)]['target'] != str(source):
                        raise ValueError(f'Conflicting targets for {dest}')
                    operations[str(dest)]['harnesses'].append(h)
                else:
                    operations[str(dest)] = {'target': str(source), 'harnesses': [h], 'kind': kind}
        for dest, operation in operations.items():
            if operation['kind'] == 'folder' and any(s.is_relative_to(dest) for s in sources):
                raise ValueError(f'A skill source lives inside a folder that would be displaced: {dest}')
        for h, total in totals.items():
            print(f'TOTAL {h}: links={total["links"]} folders={total["folders"]} '
                  f'symlinks={total["symlinks"]} files={total["files"]}')
        print(f'UNIQUE links={len(operations)} moves={sum(o["kind"] is not None for o in operations.values())}')
        return operations

    def backup(self):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        path = self.state_dir / ('backup-' + stamp)
        path.mkdir(parents=True)
        return path

    def journal(self, backup, dest, record):
        path = backup / 'manifest.json'
        data = read_json(path, {'version': 1, 'original_paths': {}})
        data['original_paths'][str(dest)] = record
        save_json(path, data)
        save_json(self.state_path, self.state)

    def apply(self):
        # The first plan does not even create state if there is no work.
        if not self.plan():
            print('No changes')
            return
        with self.locked():
            self.sources.clear()
            operations = self.plan()
            backup = None
            for dest_text, operation in operations.items():
                dest = Path(dest_text)
                record = self.state['links'].get(dest_text)
                if record is None:
                    if backup is None:
                        backup = self.backup()
                    slot = str(len(self.state['links']))
                    record = {'target': operation['target'], 'harnesses': operation['harnesses'],
                              'original': str(backup / 'originals' / slot) if exists(dest) else None,
                              'backup': str(backup), 'phase': 'prepared'}
                    self.state['links'][dest_text] = record
                    self.journal(backup, dest, record)
                original = Path(record['original']) if record['original'] else None
                if exists(dest):
                    if matches(dest, record['target']):
                        continue
                    if record['phase'] != 'prepared' or original is None or exists(original):
                        raise ValueError(f'Cannot displace changed path: {dest}')
                    move(dest, original)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.symlink_to(record['target'], target_is_directory=True)
                record['phase'] = 'linked'
                self.journal(Path(record['backup']), dest, record)
            print(f'Applied {len(operations)} links')

    def uninstall(self):
        # Without --harness every record is restored, wherever the harness lives now.
        selected_dirs = {self.directories[h].resolve() for h in self.selected}
        records = {d: r for d, r in self.state['links'].items()
                   if not self.args.harness or
                   any(Path(d).is_relative_to(directory) for directory in selected_dirs)}
        if not records:
            print('No changes')
            return
        # Preflight every restoration before moving anything.
        def untouched(d, r):
            # An apply that stopped before moving anything left nothing to restore.
            return (r.get('phase') == 'prepared' and not matches(Path(d), r['target'])
                    and not (r['original'] and exists(r['original'])))

        for d, r in records.items():
            if untouched(d, r):
                continue
            if exists(d) and not matches(Path(d), r['target']) and r.get('phase') != 'restoring':
                raise ValueError(f'Refusing to replace user changes: {d}')
            if r['original'] and not exists(r['original']) and r.get('phase') != 'restoring':
                raise ValueError(f'Original backup unavailable: {d}')
        with self.locked():
            if any(self.state['links'].get(d) != r for d, r in records.items()):
                raise ValueError('State changed during uninstall; retry')
            for d, r in records.items():
                dest = Path(d)
                backup = Path(r['backup'])
                retired = backup / 'removed-links' / hashlib.sha256(d.encode()).hexdigest()[:24]
                if untouched(d, r):
                    del self.state['links'][d]
                    self.journal(backup, dest, dict(r, phase='abandoned'))
                    print(f'UNCHANGED {dest}')
                    continue
                if r.get('phase') != 'restoring':
                    r['phase'] = 'restoring'
                    r['removed_link'] = str(retired)
                    self.journal(backup, dest, r)
                retired = Path(r['removed_link'])
                if matches(dest, r['target']):
                    if exists(retired):
                        raise ValueError(f'Removed-link backup already exists: {retired}')
                    move(dest, retired)
                if r['original'] and exists(r['original']):
                    if exists(dest):
                        raise ValueError(f'Restore destination occupied: {dest}')
                    move(r['original'], dest)
                elif exists(dest) and not r['original']:
                    raise ValueError(f'Restore destination occupied: {dest}')
                r['phase'] = 'restored'
                del self.state['links'][d]
                self.journal(backup, dest, r)
                print(f'RESTORED {dest}')

    def status(self):
        for d, r in sorted(self.state['links'].items()):
            label = 'managed' if matches(Path(d), r['target']) else 'changed or missing'
            print(f'{label}: {d} -> {r["target"]}')
        print(f'{len(self.state["links"])} managed records')

    def tools(self):
        for name, spec in self.config.get('tools', {}).items():
            print(f'TOOL {name}: version={spec["version"]}; check={spec["check"]}')
            print(f'  install: {spec["install"]}')
        print('Tool plan only; nothing installed or executed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    for name in ('plan', 'apply', 'uninstall', 'status', 'tools'):
        action.add_argument('--' + name, action='store_true')
    parser.add_argument('--harness', choices=HARNESS_NAMES)
    parser.add_argument('--home', help='Isolated home; ignores harness environment overrides')
    parser.add_argument('--manifest', default=str(Path(__file__).resolve().with_name('stack.toml')))
    parser.add_argument('--pack', action='append', default=[], help='Add an opt-in pack; repeatable')
    parser.add_argument('--private', action='store_true', help='Link the local private overlay too')
    args = parser.parse_args()
    try:
        installer = Installer(args)
        if args.plan:
            installer.plan()
        elif args.apply:
            installer.apply()
        elif args.uninstall:
            installer.uninstall()
        elif args.status:
            installer.status()
        else:
            installer.tools()
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
