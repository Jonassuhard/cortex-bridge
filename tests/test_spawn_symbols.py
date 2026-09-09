import unittest
from types import SimpleNamespace
from executor.process_spawn import resolve_addfchdir


class SpawnSymbolTests(unittest.TestCase):
    def test_sdk_version_selects_supported_symbol(self):
        old, standard = object(), object()
        library = SimpleNamespace(posix_spawn_file_actions_addfchdir_np=old,
                                  posix_spawn_file_actions_addfchdir=standard)
        self.assertIs(resolve_addfchdir(library, macos_major=14), old)
        self.assertIs(resolve_addfchdir(library, macos_major=26), standard)
        self.assertIs(resolve_addfchdir(SimpleNamespace(posix_spawn_file_actions_addfchdir_np=old),
                                      macos_major=26), old)

    def test_missing_supported_symbol_has_no_path_fallback(self):
        for library in (SimpleNamespace(), SimpleNamespace(posix_spawn_file_actions_addchdir=object())):
            with self.assertRaisesRegex(RuntimeError, "PROCESS_FCHDIR_UNAVAILABLE"):
                resolve_addfchdir(library, macos_major=26)


if __name__ == "__main__":
    unittest.main()
