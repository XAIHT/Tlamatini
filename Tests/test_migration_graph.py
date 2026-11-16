# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Run visibly with Django installed: real graphs/migrations, isolated SQLite only.

Never imports the production AgentConfig or starts its services. No manage.py,
working database, private configuration, backup or restore mechanism is used.
"""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

from django.apps import AppConfig

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tlamatini"))


class MigrationOnlyAgentConfig(AppConfig):
    name = "agent"

    def import_models(self):
        # Migration state supplies the historical models; avoid runtime startup.
        self.models = self.apps.all_models[self.label]


class ActualMigrationGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.conf import settings
        scratch = ROOT / "Temp"
        scratch.mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="migration-graph-", dir=scratch)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.folder = Path(cls.temporary.name)
        if settings.configured:
            raise RuntimeError("Run this suite separately with isolated Django settings.")
        settings.configure(
            SECRET_KEY="isolated-release-migration-test", AUTH_USER_MODEL="auth.User",
            USE_TZ=True, DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            INSTALLED_APPS=[
                "django.contrib.contenttypes", "django.contrib.auth",
                "django.contrib.admin", "django.contrib.sessions",
                __name__ + ".MigrationOnlyAgentConfig",
            ],
            DATABASES={alias: {"ENGINE": "django.db.backends.sqlite3",
                               "NAME": str(cls.folder / f"{alias}.sqlite3")}
                       for alias in ("default",)},
        )
        import django
        django.setup()
        from django.db import connections
        from django.db.migrations.loader import MigrationLoader
        cls.addClassCleanup(connections.close_all)
        cls.loader = MigrationLoader(None)
        assert not cls.loader.detect_conflicts(), cls.loader.detect_conflicts()
        leaves = cls.loader.graph.leaf_nodes("agent")
        # Exactly one agent leaf: a second one means a new migration does not
        # depend on the current last migration, and upgrades would fork.
        assert len(leaves) == 1, leaves
        cls.leaf = leaves[0]
        cls.rc = ("agent", "0224_remote_controller")
        assert cls.rc in cls.loader.disk_migrations, cls.rc
        assert cls.rc in cls.loader.graph.forwards_plan(cls.leaf), (cls.rc, cls.leaf)
        cls.parent = next(n for n in cls.loader.disk_migrations[cls.rc].dependencies
                          if n[0] == "agent")
        cls.targets = cls.loader.graph.leaf_nodes()
        print(f"REAL {ROOT.name}: {len(cls.loader.disk_migrations)} graph nodes; "
              f"{cls.rc[1]} follows {cls.parent[1]}; agent leaf {cls.leaf[1]}", flush=True)

    def setUp(self):
        from django.db import connections
        connections.close_all()
        # Historical data migrations intentionally use the product's default
        # alias. Give each test a fresh default database, not a second alias.
        connections["default"].settings_dict["NAME"] = str(
            self.folder / (self._testMethodName + ".sqlite3"))

    def tearDown(self):
        from django.db import connections
        connections.close_all()

    def executor(self, alias):
        from django.db import connections
        from django.db.migrations.executor import MigrationExecutor
        return MigrationExecutor(connections[alias])

    def test_graph_matches_this_editions_actual_handoff(self):
        expected = ("0227_create_superuser_console_handoff"
                    if (ROOT / "Tlamatini/agent/migrations/0227_create_superuser_console_handoff.py").exists()
                    else "0223_create_superuser_console_handoff")
        self.assertEqual(self.parent, ("agent", expected))

    def test_fresh_database_applies_the_complete_graph(self):
        executor = self.executor("default")
        executor.migrate(self.targets)
        executor = self.executor("default")
        self.assertEqual(executor.migration_plan(self.targets), [])
        apps = executor.loader.project_state(self.targets).apps
        user = apps.get_model("auth", "User").objects.create(
            username="migration-fresh", password="!")
        profile = apps.get_model("agent", "RemoteControllerProfile").objects.create(user=user)
        self.assertIsInstance(profile.account, uuid.UUID)
        self.assertFalse(profile.enabled)
        self.assertEqual(profile.binding_id, "")
        revocations = apps.get_model("agent", "RemoteControllerRevocation").objects
        revocations.create(binding_id="a" * 32, account=profile.account, adapter=profile.adapter)
        self.assertEqual(revocations.count(), 1)
        print("PASS real fresh SQLite: full graph, user, remote profile and revocation", flush=True)

    def test_upgrade_and_reverse_preserve_existing_account_and_prompt(self):
        prior = [node for node in self.targets if node[0] != "agent"] + [self.parent]
        executor = self.executor("default")
        executor.migrate(prior)
        apps = executor.loader.project_state(prior).apps
        user = apps.get_model("auth", "User").objects.create(username="migration-existing", password="!")
        prompts = apps.get_model("agent", "Prompt").objects
        self.assertTrue(prompts.filter(pk=1).exists())
        prompts.filter(pk=1).update(promptContent="Preserve this user-edited prompt.")
        executor = self.executor("default")
        graph = executor.loader.graph
        before = set(graph.forwards_plan(self.parent))
        expected = [name for app, name in graph.forwards_plan(self.leaf)
                    if app == "agent" and (app, name) not in before]
        self.assertEqual(expected[:1], [self.rc[1]])
        self.assertEqual([migration.name for migration, backwards in executor.migration_plan(self.targets)],
                         expected)
        executor.migrate(self.targets)
        apps = executor.loader.project_state(self.targets).apps
        self.assertTrue(apps.get_model("auth", "User").objects.filter(pk=user.pk, username=user.username).exists())
        self.assertEqual(apps.get_model("agent", "Prompt").objects.get(pk=1).promptContent,
                         "Preserve this user-edited prompt.")
        apps.get_model("agent", "RemoteControllerProfile").objects.create(user_id=user.pk)
        executor = self.executor("default")
        executor.migrate(prior)
        apps = executor.loader.project_state(prior).apps
        self.assertTrue(apps.get_model("auth", "User").objects.filter(pk=user.pk).exists())
        self.assertEqual(apps.get_model("agent", "Prompt").objects.get(pk=1).promptContent,
                         "Preserve this user-edited prompt.")
        self.executor("default").migrate(self.targets)
        self.assertEqual(self.executor("default").migration_plan(self.targets), [])
        print("PASS real existing-account upgrade, reverse and reapply; user and prompt retained", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
