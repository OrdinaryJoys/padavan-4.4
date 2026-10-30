#!/usr/bin/env python3
"""Exact directive edits preserve domain names and unrelated restriction policy."""
import unittest
from test_startup_config_policy import StartupPolicyFixture


class DnsMigrationTests(StartupPolicyFixture):
    def test_domain_names_are_not_deleted_as_directives(self):
        retained=['server=/filter-aaaa.example/192.0.2.53',
                  'address=/my-filter-aaaa.test/192.0.2.1',
                  '# preserve this comment about filter-aaaa',
                  'server=/min-ttl.example/192.0.2.54',
                  'dhcp-ignore=tag:untrusted']
        for enabled in ('0','1'):
            with self.subTest(enabled=enabled):
                self.custom.write_text('\n'.join(retained+['filter-aaaa','  filter-aaaa  # old toggle'])+'\n')
                result=self.run_script('dns',FILTER_AAAA=enabled)
                self.assertEqual(result.returncode,0,result.stderr)
                lines=self.custom.read_text().splitlines()
                for line in retained:self.assertIn(line,lines)
                self.assertEqual(lines.count('filter-aaaa'),int(enabled))
                self.assertNotIn('  filter-aaaa  # old toggle',lines)


if __name__=='__main__':
    unittest.main()
