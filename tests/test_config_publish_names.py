"""Optimized real validator and bounded backup naming, in private trees only."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'trunk/user/scripts/storage_validate.c'


class ConfigPublishNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-publish-names-')
        cls.root = Path(cls.temp.name).resolve()
        cls.operation, cls.stage = cls.root / 'operation', cls.root / 'stage'
        cls.stage.mkdir(mode=0o700)
        gcc = shutil.which('gcc-16') or shutil.which('gcc')
        if not gcc or not shutil.which('clang'):
            raise AssertionError('Genuine GNU GCC and Clang required')
        version = subprocess.check_output([gcc, '--version'], text=True, timeout=10)
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('GNU compiler resolved to a different compiler')
        helper = cls.root / 'names.c'
        helper.write_text('#define main storage_validate_program_main\n#include "' +
                          str(SOURCE) + '"\n#undef main\n' + r'''
int main(int argc, char **argv)
{
 struct { unsigned char before[8], out[256], after[8]; } value;
 char *out; const char *leaf; int result;
 if (argc != 5) return 64;
 memset(&value, 0xa5, sizeof(value));
 out = !strcmp(argv[1], "null-out") ? NULL : (char *)value.out;
 leaf = !strcmp(argv[1], "null-leaf") ? NULL : argv[2];
 result = scp_backup_name(out, (size_t)strtoul(argv[4], NULL, 10), leaf,
                          (unsigned int)strtoul(argv[3], NULL, 10));
 printf("%d\n", result);
 return fwrite(&value, 1, sizeof(value), stdout) == sizeof(value) ? 0 : 65;
}
''')
        cls.programs, cls.helpers = [], []
        for label, compiler in (('gcc', gcc), ('clang', shutil.which('clang'))):
            flags = ['-std=gnu99', '-O2', '-Wall', '-Wextra', '-Werror']
            if label == 'clang':
                flags += ['-fsanitize=address,undefined']
            flags += ['-DSTARTUP_CONFIG_TEST_UID=geteuid()',
                      '-DSTORAGE_OPERATION_DIR="' + str(cls.operation) + '"',
                      '-DSTARTUP_CONFIG_STAGE_DIR="' + str(cls.stage) + '"']
            for source, output, collection in ((SOURCE, label + '-validator', cls.programs),
                                                (helper, label + '-names', cls.helpers)):
                binary = cls.root / output
                run = subprocess.run([compiler, *flags, str(source), '-o', str(binary)],
                                     capture_output=True, text=True, timeout=60)
                if run.returncode or run.stderr:
                    raise AssertionError(run.stderr)
                collection.append(binary)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_program(self, binary, args):
        run = subprocess.run([str(binary), *map(str, args)], capture_output=True,
                             timeout=10)
        self.assertNotIn(b'AddressSanitizer', run.stderr)
        self.assertNotIn(b'runtime error:', run.stderr)
        return run

    def test_optimized_actual_validator_accepts_a_private_storage_archive(self):
        archive = self.root / 'valid.tar'
        with tarfile.open(archive, 'w', format=tarfile.USTAR_FORMAT) as stream:
            member = tarfile.TarInfo('start_script.sh')
            body = b'#!/bin/sh\n'
            member.size, member.mode = len(body), 0o755
            stream.addfile(member, io.BytesIO(body))
        for binary in self.programs:
            with self.subTest(compiler=binary.name):
                run = self.run_program(binary, [archive, str(4 * 1024 * 1024)])
                self.assertEqual((run.returncode, run.stderr), (0, b''))

    def test_exact_name_capacity_and_rejection_preserve_all_guard_bytes(self):
        cases = [('x' * 220, 0, 238, True), ('x' * 220, 9, 240, True),
                 ('x' * 220, 9, 239, False), ('x' * 220, 0, 237, False),
                 ('x' * 221, 0, 256, False), ('', 0, 256, False),
                 ('.', 0, 256, False), ('..', 0, 256, False),
                 ('bad/name', 0, 256, False), ('config', 10, 256, False),
                 ('config', 4294967295, 256, False), ('config', 0, 0, False),
                 ('界' * 73 + 'x', 9, 240, True)]
        for binary in self.helpers:
            for leaf, slot, capacity, valid in cases:
                with self.subTest(compiler=binary.name, leaf=leaf, slot=slot, capacity=capacity):
                    run = self.run_program(binary, ['name', leaf, slot, capacity])
                    self.assertEqual(run.returncode, 0, run.stderr)
                    ret, raw = run.stdout.split(b'\n', 1)
                    self.assertEqual(ret, b'0' if valid else b'-1')
                    expected = bytearray(b'\xa5' * 272)
                    if valid:
                        name = leaf.encode() + b'.before-migration' + (b'.9' if slot else b'') + b'\0'
                        expected[8:8 + len(name)] = name
                    self.assertEqual(raw, bytes(expected))
            for mode in ('null-out', 'null-leaf'):
                run = self.run_program(binary, [mode, 'config', 0, 256])
                self.assertEqual(run.stdout, b'-1\n' + b'\xa5' * 272)
                self.assertEqual(run.returncode, 0)

    def publication(self, binary, leaf, reuse=False):
        directory = Path(tempfile.mkdtemp(prefix='case-', dir=self.root))
        parent = directory / 'storage'; parent.mkdir(mode=0o755)
        inputs = directory / 'inputs'; inputs.mkdir(mode=0o700)
        old, new = b'old validated policy\n', b'new validated policy\n'
        destination, original, candidate = parent / leaf, inputs / 'original', inputs / 'candidate'
        for path, data in ((destination, old), (original, old), (candidate, new)):
            path.write_bytes(data); path.chmod(0o600)
        inode = destination.stat().st_ino
        if reuse:
            backup = parent / '.config-backups'; backup.mkdir(mode=0o700)
            os.link(destination, backup / (leaf + '.before-migration.9'))
        elif len(leaf.encode()) == 220:
            for slot in range(9):
                suffix = '.before-migration' + ('.' + str(slot) if slot else '')
                (parent / (leaf + suffix)).write_bytes(b'occupied legacy slot\n')
        run = self.run_program(binary, ['--publish-config', candidate, original, destination])
        return run, destination, candidate, inode, old, new

    def test_longest_leaf_publishes_and_reuses_the_exact_slot_nine_inode(self):
        for binary in self.programs:
            for reuse in (False, True):
                with self.subTest(compiler=binary.name, reuse=reuse):
                    run, destination, candidate, inode, old, new = self.publication(binary, 'x' * 220, reuse)
                    self.assertEqual((run.returncode, run.stderr), (0, b''))
                    backup = Path(run.stdout.decode().strip())
                    self.assertEqual(backup.name, 'x' * 220 + '.before-migration.9')
                    self.assertEqual((backup.stat().st_ino, backup.read_bytes()), (inode, old))
                    self.assertEqual(destination.read_bytes(), new)
                    self.assertEqual(candidate.read_bytes(), new)
                    self.assertEqual(list(self.stage.iterdir()), [])

    def test_overlong_leaf_refuses_without_replacing_or_backing_up_destination(self):
        for binary in self.programs:
            with self.subTest(compiler=binary.name):
                run, destination, candidate, inode, old, new = self.publication(binary, 'x' * 221)
                self.assertEqual(run.returncode, 1)
                self.assertEqual(run.stdout, b'')
                self.assertEqual((destination.stat().st_ino, destination.read_bytes()), (inode, old))
                self.assertEqual(candidate.read_bytes(), new)
                self.assertFalse((destination.parent / '.config-backups').exists())
                self.assertEqual(list(self.stage.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
