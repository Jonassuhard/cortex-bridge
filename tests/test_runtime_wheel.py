"""Real wheel boundary; builds in temporary storage, never the checkout."""
import os
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


class RuntimeWheelTests(unittest.TestCase):
    def test_wheel_contains_runtime_modules_and_imports_outside_checkout(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "source"
            source.mkdir()
            shutil.copy2(root / "pyproject.toml", source / "pyproject.toml")
            for name in ("console", "executor", "orchestration", "transport"):
                shutil.copytree(root / name, source / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            environment = {"PATH": os.defpath, "HOME": str(temporary),
                "CORTEX_HOME": str(temporary / "runtime"), "PYTHONDONTWRITEBYTECODE": "1",
                "PIP_CONFIG_FILE": os.devnull, "PIP_INDEX_URL": "https://pypi.org/simple",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
            built = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps",
                "--wheel-dir", str(temporary / "wheels"), str(source)],
                env=environment, cwd=temporary, capture_output=True, text=True, timeout=120)
            self.assertEqual(built.returncode, 0, built.stderr[-3000:])
            wheel, = (temporary / "wheels").glob("cortex_bridge-*.whl")
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
            missing = [path.name for path in sorted((root / "console").glob("*.py"))
                       if path.name not in names]
            self.assertEqual(missing, [], "Runtime modules omitted from the actual wheel")
            modules = ["effect_gate", "runtime_exclusion", "process_helper_build", "install_resource_tree",
                       "generation_metadata", "generation_publication", "generation_install", "managed_runtime", "bootstrap_install",
                       "chrome_extension", "storage_lock", "lifecycle_lock", "storage_result",
                       "orchestration.loop", "executor.effect_recovery", "executor.process_spawn", "server"]
            program = (
                "import importlib,sys\n"
                f"wheel={str(wheel)!r}\nsys.path.insert(0,wheel)\n"
                f"for name in {modules!r}:\n"
                " module=importlib.import_module(name)\n"
                " assert module.__file__.startswith(wheel+'/'), (name,module.__file__)\n"
                "print('WHEEL_IMPORTS_VERIFIED')\n")
            checked = subprocess.run([sys.executable, "-I", "-c", program], cwd=temporary,
                env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(checked.returncode, 0, checked.stderr[-3000:])
            self.assertEqual(checked.stdout.strip(), "WHEEL_IMPORTS_VERIFIED")
            # Install the real wheel, then exercise its static HTTP routes with
            # resources assembled by production code, outside the checkout.
            app = temporary / "generation/app"
            app.mkdir(parents=True, mode=0o700)
            installed_python = app / "python"
            installed = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps",
                "--no-compile", "--target", str(installed_python), str(wheel)],
                env=environment, cwd=temporary, capture_output=True, text=True, timeout=60)
            self.assertEqual(installed.returncode, 0, installed.stderr[-3000:])
            from install_resource_tree import stage_application_resources, verify_application_resources
            source_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            app_fd = os.open(app, os.O_RDONLY | os.O_DIRECTORY)
            try:
                resources = stage_application_resources(source_fd, app_fd)
                verify_application_resources(app_fd, resources)
            finally:
                os.close(app_fd)
                os.close(source_fd)
            asset = next(iter(sorted((root / "frontend/out/_next").rglob("*.js"))))
            urls = {"/": hashlib.sha256((root / "frontend/out/index.html").read_bytes()).hexdigest(),
                    "/" + str(asset.relative_to(root / "frontend/out")): hashlib.sha256(asset.read_bytes()).hexdigest()}
            static_program = (
                "import asyncio,hashlib,sys\nfrom pathlib import Path\n"
                f"installed=Path({str(installed_python)!r})\nsys.path.insert(0,str(installed))\n"
                "import server\nassert Path(server.__file__).parent == installed\n"
                "async def check():\n"
                f" for url,expected in {urls!r}.items():\n"
                "  messages=[]\n"
                "  async def send(message): messages.append(message)\n"
                "  async def receive(): return {'type':'http.request','body':b'','more_body':False}\n"
                "  scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},'http_version':'1.1',"
                "'method':'GET','scheme':'http','path':url,'raw_path':url.encode(),'query_string':b'',"
                "'root_path':'','headers':[],'server':('127.0.0.1',8420),'client':('127.0.0.1',12345)}\n"
                "  await server.app(scope,receive,send)\n"
                "  assert messages[0]['status']==200, (url,messages[0])\n"
                "  body=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')\n"
                "  assert hashlib.sha256(body).hexdigest()==expected, url\n"
                "asyncio.run(check())\nprint('INSTALLED_STATIC_ROUTES_VERIFIED')\n")
            routed = subprocess.run([sys.executable, "-I", "-c", static_program], cwd=temporary,
                env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(routed.returncode, 0, routed.stderr[-3000:])
            self.assertEqual(routed.stdout.strip(), "INSTALLED_STATIC_ROUTES_VERIFIED")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases() == 0:
        raise SystemExit("No tests collected")
    result = unittest.TextTestRunner().run(suite)
    raise SystemExit(not result.wasSuccessful())
