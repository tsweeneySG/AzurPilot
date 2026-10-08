"""共用配置编辑：共识、混合字段与身份锁定。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from module.api.config_service import ROOT, ConfigService
from module.api.protocol import ApiError, ConfigChange
from module.webui.common_editor import MIXED_SENTINEL, common_editor_instances


def fixture(directory):
    """只复制参数表和模板，测试不碰用户配置。"""
    root = Path(directory)
    (root / 'config').mkdir()
    (root / 'module/config/argument').mkdir(parents=True)
    (root / 'module/config/i18n').mkdir(parents=True)
    for relative in ['module/config/argument/args.json', 'module/config/argument/menu.json',
                     'module/config/i18n/zh-CN.json', 'config/template.json']:
        shutil.copyfile(ROOT / relative, root / relative)
    shutil.copyfile(ROOT / 'config/template.json', root / 'config/testpilot.json')
    return root


class CommonEditorInstanceTests(unittest.TestCase):
    def test_skips_template_all_and_mod_suffixes(self):
        names = common_editor_instances(['alpha', 'template', 'All', 'bridge.maa', 'bridge.fpy', 'my.pilot'])
        self.assertEqual(['alpha', 'my.pilot'], names)


class CommonConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = ConfigService(fixture(self.temp.name))

    def _write(self, name, enable, campaign):
        data = self.service.read(name)[0]
        data['Main']['Scheduler']['Enable'] = enable
        data['Main']['Campaign']['Name'] = campaign
        self.service.path(name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_consensus_marks_disagreement_and_skips_non_alas_profiles(self):
        source = self.service.path('testpilot').read_text(encoding='utf-8')
        other = self.service.directory / 'other.json'
        other.write_text(source, encoding='utf-8')
        maa = self.service.directory / 'bridge.maa.json'
        maa.write_text(source, encoding='utf-8')
        self._write('testpilot', True, '12-4')
        self._write('other', False, '7-2')
        maa_before = maa.read_bytes()
        view = self.service.consensus()
        self.assertEqual(['other', 'testpilot'], view['instances'])
        self.assertIn('Main.Scheduler.Enable', view['mixed'])
        self.assertIn('Main.Campaign.Name', view['mixed'])
        self.assertIn('Alas.Emulator.Serial', view['locked'])
        self.assertNotIn('Main.Scheduler.Enable', view['locked'])
        self.assertEqual(maa_before, maa.read_bytes())

    def test_agreement_is_not_mixed(self):
        self._write('testpilot', True, '12-4')
        view = self.service.consensus()
        self.assertNotIn('Main.Scheduler.Enable', view['mixed'])
        self.assertTrue(view['values']['Main']['Scheduler']['Enable'])

    def test_patch_writes_only_the_changed_field(self):
        source = self.service.path('testpilot').read_text(encoding='utf-8')
        (self.service.directory / 'other.json').write_text(source, encoding='utf-8')
        self._write('testpilot', False, '12-4')
        self._write('other', False, '7-2')
        view = self.service.patch_common([ConfigChange(path='Main.Scheduler.Enable', value=True)])
        self.assertNotIn('Main.Scheduler.Enable', view['mixed'])
        self.assertIn('Main.Campaign.Name', view['mixed'])
        for name in ('testpilot', 'other'):
            data = json.loads(self.service.path(name).read_text(encoding='utf-8'))
            self.assertTrue(data['Main']['Scheduler']['Enable'])
        self.assertEqual('12-4', json.loads(self.service.path('testpilot').read_text(encoding='utf-8'))['Main']['Campaign']['Name'])
        self.assertEqual('7-2', json.loads(self.service.path('other').read_text(encoding='utf-8'))['Main']['Campaign']['Name'])

    def test_locked_identity_and_sentinel_are_rejected_without_writing(self):
        path = self.service.path('testpilot')
        before = path.read_bytes()
        with self.assertRaises(ApiError) as locked:
            self.service.patch_common([ConfigChange(path='Alas.Emulator.Serial', value='127.0.0.1:5555')])
        self.assertEqual('READ_ONLY', locked.exception.code)
        self.assertEqual(before, path.read_bytes())
        with self.assertRaises(ApiError) as mixed:
            self.service.patch_common([ConfigChange(path='Main.Campaign.Name', value=MIXED_SENTINEL)])
        self.assertEqual('INVALID_PARAMS', mixed.exception.code)
        self.assertEqual(before, path.read_bytes())

    def test_zero_profiles(self):
        self.service.path('testpilot').unlink()
        view = self.service.consensus()
        self.assertEqual([], view['instances'])
        self.assertEqual({}, view['values'])
        with self.assertRaises(ApiError) as error:
            self.service.patch_common([ConfigChange(path='Main.Scheduler.Enable', value=True)])
        self.assertEqual('NOT_FOUND', error.exception.code)
