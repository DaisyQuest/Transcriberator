import json
import unittest
from pathlib import Path


class TestSharedContractsV1(unittest.TestCase):
    def setUp(self):
        self.schema_dir = Path('modules/shared-contracts/schemas/v1')
        self.expected_schemas = {
            'project.schema.json': {'id', 'ownerId', 'name', 'createdAt', 'updatedAt'},
            'audio_asset.schema.json': {
                'id',
                'projectId',
                'sourceBlobUri',
                'normalizedBlobUri',
                'format',
                'durationMs',
                'sampleRateHz',
                'channels',
                'createdAt',
            },
            'job.schema.json': {
                'id',
                'projectId',
                'audioAssetId',
                'mode',
                'status',
                'pipelineVersion',
                'configVersion',
                'createdAt',
                'updatedAt',
            },
            'stage_run.schema.json': {
                'id',
                'jobId',
                'stageName',
                'attempt',
                'status',
                'inputArtifactUris',
                'outputArtifactUris',
                'createdAt',
                'updatedAt',
            },
            'score_revision.schema.json': {
                'id',
                'projectId',
                'parentRevisionId',
                'jobId',
                'musicXmlUri',
                'midiUri',
                'pdfUri',
                'pngUri',
                'irVersion',
                'createdAt',
            },
        }

    def _load_schema(self, name):
        path = self.schema_dir / name
        self.assertTrue(path.is_file(), f'Missing schema file: {path}')
        data = json.loads(path.read_text(encoding='utf-8'))
        return data

    def test_expected_schema_files_present(self):
        actual = {p.name for p in self.schema_dir.glob('*.json')}
        self.assertEqual(actual, set(self.expected_schemas.keys()))

    def test_each_schema_is_json_schema_object(self):
        for schema_name in self.expected_schemas:
            with self.subTest(schema=schema_name):
                schema = self._load_schema(schema_name)
                self.assertEqual(schema.get('type'), 'object')
                self.assertIn('$schema', schema)
                self.assertIn('$id', schema)
                self.assertFalse(schema.get('additionalProperties', True))
                self.assertIn('properties', schema)
                self.assertIn('required', schema)

    def test_required_fields_match_expected_contract(self):
        for schema_name, required_fields in self.expected_schemas.items():
            with self.subTest(schema=schema_name):
                schema = self._load_schema(schema_name)
                self.assertEqual(set(schema['required']), required_fields)

    def test_critical_enums_are_defined(self):
        audio_schema = self._load_schema('audio_asset.schema.json')
        self.assertEqual(audio_schema['properties']['format']['enum'], ['mp3', 'wav', 'flac'])

        job_schema = self._load_schema('job.schema.json')
        self.assertEqual(job_schema['properties']['mode']['enum'], ['draft', 'hq'])
        self.assertEqual(
            job_schema['properties']['status']['enum'],
            ['queued', 'running', 'succeeded', 'failed', 'cancelled'],
        )

        stage_schema = self._load_schema('stage_run.schema.json')
        self.assertIn('decode_normalize', stage_schema['properties']['stageName']['enum'])
        self.assertIn('engraving', stage_schema['properties']['stageName']['enum'])
        self.assertIn('skipped', stage_schema['properties']['status']['enum'])

    def test_contract_documentation_and_policy_exist(self):
        domain_doc = Path('modules/shared-contracts/Domain_Entities_v1.md')
        policy_doc = Path('modules/shared-contracts/Compatibility_Policy.md')

        self.assertTrue(domain_doc.is_file())
        self.assertTrue(policy_doc.is_file())

        domain_text = domain_doc.read_text(encoding='utf-8')
        policy_text = policy_doc.read_text(encoding='utf-8')

        for entity_name in ['Project', 'AudioAsset', 'Job', 'StageRun', 'ScoreRevision']:
            with self.subTest(entity_name=entity_name):
                self.assertIn(f'### {entity_name}', domain_text)

        required_policy_snippets = [
            'Patch changes',
            'Minor changes',
            'Major changes',
            'must include:',
            'ignore unknown fields',
        ]
        for snippet in required_policy_snippets:
            with self.subTest(policy_snippet=snippet):
                self.assertIn(snippet, policy_text)


if __name__ == '__main__':
    unittest.main()
