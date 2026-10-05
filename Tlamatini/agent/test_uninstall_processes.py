# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Actual owned-worker cleanup, scoped to a temporary installation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uninstall_processes as cleanup


class UninstallWorkerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tlamatini-workers-"))
        self.procs = []
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(self.stop_fixtures)

    def stop_fixtures(self):
        for proc in self.procs:
            try:
                children = psutil.Process(proc.pid).children(recursive=True)
                proc.kill()
                for child in children:
                    child.kill()
                proc.wait(timeout=5)
            except (psutil.NoSuchProcess, ProcessLookupError):
                pass
            finally:
                # psutil may have already reaped the process. Consume the
                # Popen handle too, so a successfully stopped fixture cannot
                # leave a stale returncode or ResourceWarning behind.
                proc.wait(timeout=5)

    def spawn(self, args, cwd, env=None):
        proc = subprocess.Popen([sys.executable, *args], cwd=cwd, env=env)
        self.procs.append(proc)
        return proc

    def test_path_boundary_and_arguments(self):
        agents = str(self.root / "agents")
        self.assertTrue(cleanup.command_path('--config=' + agents + '/tool/config.yaml', agents))
        self.assertFalse(cleanup.command_path(str(self.root) + '-another/agents/tool.py', str(self.root)))
        self.assertFalse(cleanup.command_path('print("' + agents + '")', agents))
        self.assertFalse(cleanup.command_path('https://example.test/' + agents, agents))

    def test_external_python_absolute_agent_path_is_stopped(self):
        agent = self.root / "agents/shoter/ownership_probe.py"
        agent.parent.mkdir(parents=True)
        agent.write_text('import time; time.sleep(90)', encoding='utf-8')
        proc = self.spawn([str(agent)], str(self.root.parent))
        report = cleanup.stop_owned_workers(str(self.root))
        self.assertIn(proc.pid, [row['pid'] for row in report['stopped']])
        proc.wait(timeout=5)
        self.assertEqual(report['survivors'], [])

    def test_relative_agent_path_and_external_child_are_stopped_but_unrelated_survives(self):
        agent_dir = self.root / 'agents/pools/fixture/sleeper_7'
        agent_dir.mkdir(parents=True)
        child_record = self.root / 'child.json'
        script = agent_dir / 'worker.py'
        script.write_text(
            'import subprocess,sys,time,json\n'
            + f'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(90)"],cwd={str(self.root.parent)!r})\n'
            + f'open({str(child_record)!r},"w").write(json.dumps({{"pid":p.pid}}))\n'
            + 'time.sleep(90)\n', encoding='utf-8')
        unrelated = self.spawn(['-c', 'import time; time.sleep(90)'], str(self.root.parent))
        owned = self.spawn(['worker.py'], str(agent_dir))
        for _ in range(100):
            if child_record.is_file() and child_record.stat().st_size:
                break
            time.sleep(.05)
        child_pid = json.loads(child_record.read_text())['pid']
        child = psutil.Process(child_pid)
        report = cleanup.stop_owned_workers(str(self.root))
        stopped = {row['pid'] for row in report['stopped']}
        self.assertIn(owned.pid, stopped)
        self.assertIn(child_pid, stopped)
        self.assertFalse(child.is_running())
        self.assertIsNone(unrelated.poll())
        self.assertNotIn(os.getpid(), stopped)
        self.assertEqual(report['survivors'], [])
        owned.wait(timeout=5)

    def test_every_actual_agent_directory_is_in_scope(self):
        source = Path(__file__).parent / 'agents'
        names = sorted(p.name for p in source.iterdir()
                       if p.is_dir() and (p / (p.name + '.py')).is_file())
        self.assertGreaterEqual(len(names), 80)
        for offset in range(0, len(names), 12):
            expected = set()
            for name in names[offset:offset + 12]:
                directory = self.root / 'agents' / name
                directory.mkdir(parents=True)
                proc = self.spawn(['-c', 'import time; time.sleep(90)'], str(directory))
                expected.add(proc.pid)
            report = cleanup.stop_owned_workers(str(self.root))
            self.assertTrue(expected <= {row['pid'] for row in report['stopped']})
            self.assertEqual(report['survivors'], [])
        print(f'Worker ownership verified across {len(names)} actual agent directories.', flush=True)

    def test_orphan_with_external_cwd_is_found_by_inherited_agent_identity(self):
        agent_dir = self.root / 'agents/pools/orphan_fixture'
        agent_dir.mkdir(parents=True)
        record = self.root / 'orphan.json'
        script = agent_dir / 'parent.py'
        script.write_text(
            'import subprocess,sys,json\n'
            + f'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(90)"],cwd={str(self.root.parent)!r})\n'
            + f'open({str(record)!r},"w").write(json.dumps({{"pid":p.pid}}))\n', encoding='utf-8')
        env = {**os.environ, 'TLAMATINI_AGENTS_ROOT': str(self.root / 'agents')}
        parent = self.spawn([str(script)], str(agent_dir), env=env)
        parent.wait(timeout=10)
        child = psutil.Process(json.loads(record.read_text())['pid'])
        self.addCleanup(lambda: child.kill() if child.is_running() else None)
        unrelated_env = {**os.environ, 'TLAMATINI_AGENTS_ROOT': str(self.root) + '-other/agents'}
        unrelated = self.spawn(['-c', 'import time; time.sleep(90)'], str(self.root.parent), env=unrelated_env)
        report = cleanup.stop_owned_workers(str(self.root))
        self.assertFalse(child.is_running())
        self.assertIsNone(unrelated.poll())
        self.assertIn(child.pid, {row['pid'] for row in report['stopped']})
        self.assertEqual(report['survivors'], [])
