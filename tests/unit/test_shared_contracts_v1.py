import json
import unittest
from pathlib import Path


class TestSharedContractsV1(unittest.TestCase):
    def setUp(self):
        self.schema_dir = Path('modules/shared-contracts/schemas/v1')
        self.base_required_schemas = {
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
        self.phase1_required_schemas = {
            'score_ir.schema.json',
            'worker_rpc.schema.json',
            'stage_state_contract.schema.json',
        }

    def _load_json(self, path):
        self.assertTrue(path.is_file(), f'Missing file: {path}')
        return json.loads(path.read_text(encoding='utf-8'))

    def _load_schema(self, name):
        return self._load_json(self.schema_dir / name)

    def test_expected_schema_files_present(self):
        actual = {p.name for p in self.schema_dir.glob('*.json')}
        expected = set(self.base_required_schemas) | self.phase1_required_schemas
        self.assertEqual(actual, expected)

    def test_each_schema_is_json_schema_object(self):
        for schema_name in sorted(set(self.base_required_schemas) | self.phase1_required_schemas):
            with self.subTest(schema=schema_name):
                schema = self._load_schema(schema_name)
                self.assertEqual(schema.get('type'), 'object')
                self.assertIn('$schema', schema)
                self.assertIn('$id', schema)
                self.assertFalse(schema.get('additionalProperties', True))
                self.assertIn('properties', schema)
                self.assertIn('required', schema)

    def test_required_fields_match_expected_contract_for_domain_entities(self):
        for schema_name, required_fields in self.base_required_schemas.items():
            with self.subTest(schema=schema_name):
                schema = self._load_schema(schema_name)
                self.assertEqual(set(schema['required']), required_fields)

    def test_critical_enums_are_defined_for_domain_entities(self):
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

    def test_dt004_score_ir_schema_contains_required_contract_components(self):
        schema = self._load_schema('score_ir.schema.json')
        self.assertEqual(schema['properties']['irVersion']['const'], 'v1')

        defs = schema['$defs']
        for node in ['globalMaps', 'part', 'measure', 'voice', 'event', 'noteEvent', 'restEvent']:
            with self.subTest(node=node):
                self.assertIn(node, defs)

        self.assertEqual(defs['noteEvent']['properties']['pitchMidi']['minimum'], 0)
        self.assertEqual(defs['noteEvent']['properties']['pitchMidi']['maximum'], 127)
        self.assertEqual(defs['noteEvent']['properties']['velocity']['minimum'], 1)
        self.assertEqual(defs['noteEvent']['properties']['velocity']['maximum'], 127)

    def test_dt004_score_ir_examples_cover_valid_and_invalid_discriminator_paths(self):
        examples_dir = Path('modules/shared-contracts/examples/v1')
        valid = self._load_json(examples_dir / 'score_ir_valid_minimal.json')
        invalid = self._load_json(examples_dir / 'score_ir_invalid_unknown_event.json')

        valid_events = valid['parts'][0]['measures'][0]['voices'][0]['events']
        self.assertEqual(valid_events[0]['type'], 'note')
        self.assertEqual(valid_events[1]['type'], 'rest')

        invalid_events = invalid['parts'][0]['measures'][0]['voices'][0]['events']
        self.assertEqual(invalid_events[0]['type'], 'chord')
        allowed_types = {'note', 'rest'}
        self.assertNotIn(invalid_events[0]['type'], allowed_types)

    def test_dt005_worker_rpc_schema_has_operations_error_and_idempotency_contracts(self):
        schema = self._load_schema('worker_rpc.schema.json')
        self.assertEqual(schema['properties']['contractVersion']['const'], 'v1')

        operation_enum = schema['$defs']['operation']['properties']['name']['enum']
        self.assertEqual(operation_enum, ['separation', 'transcription', 'quantization', 'engraving'])

        response_all_of = schema['$defs']['responseShape']['allOf']
        self.assertEqual(len(response_all_of), 2)

        key_pattern = schema['$defs']['requestShape']['properties']['idempotencyKey']['pattern']
        self.assertEqual(key_pattern, '^[A-Za-z0-9:_\\-]{16,128}$')

        envelope_categories = schema['$defs']['errorEnvelope']['properties']['category']['enum']
        self.assertIn('timeout', envelope_categories)
        self.assertIn('validation', envelope_categories)

    def test_dt006_stage_state_schema_contains_dag_retry_resume_and_degradation_contract(self):
        schema = self._load_schema('stage_state_contract.schema.json')
        self.assertEqual(schema['properties']['contractVersion']['const'], 'v1')

        stages = schema['properties']['stageOrder']['items']['enum']
        self.assertEqual(stages[0], 'decode_normalize')
        self.assertEqual(stages[-1], 'engraving')

        status_enum = schema['properties']['statuses']['items']['enum']
        for required in ['retry_wait', 'cancelled', 'skipped']:
            with self.subTest(required_status=required):
                self.assertIn(required, status_enum)

        retry_policy = schema['$defs']['retryPolicy']['properties']
        self.assertEqual(retry_policy['backoffStrategy']['enum'], ['exponential'])
        self.assertIn('decorrelated', retry_policy['jitter']['enum'])

        resume_semantics = schema['$defs']['resumeSemantics']['properties']
        self.assertEqual(resume_semantics['resumeFrom']['enum'], ['latest_successful_stage'])
        self.assertTrue(resume_semantics['requiresCheckpointArtifacts']['const'])
        self.assertTrue(resume_semantics['idempotentReentry']['const'])

    def test_contract_documentation_and_policy_exist(self):
        docs = {
            'modules/shared-contracts/Domain_Entities_v1.md': [
                '### Project',
                '### AudioAsset',
                '### Job',
                '### StageRun',
                '### ScoreRevision',
            ],
            'modules/shared-contracts/Compatibility_Policy.md': [
                'Patch changes',
                'Minor changes',
                'Major changes',
                'must include:',
                'ignore unknown fields',
            ],
            'modules/shared-contracts/Score_IR_v1.md': [
                'Validation Rules',
                'globalMaps',
                'parts',
                'voices',
                'events',
            ],
            'modules/shared-contracts/Worker_RPC_v1.md': [
                'Error Envelope (v1)',
                'Idempotency Key Semantics',
                'separation',
                'transcription',
                'quantization',
                'engraving',
            ],
            'modules/shared-contracts/Orchestrator_Stage_State_v1.md': [
                'Stage Status Set',
                'Retry/Backoff Contract',
                'Resume Semantics',
                'Graceful Degradation',
            ],
            'modules/orchestrator/Contract_Adapter_Notes.md': [
                'Source of Truth',
                'Adapter Expectations',
                'Minimal Runtime Checklist',
            ],
        }

        for doc_path, snippets in docs.items():
            with self.subTest(doc_path=doc_path):
                text = Path(doc_path).read_text(encoding='utf-8')
                for snippet in snippets:
                    with self.subTest(snippet=snippet):
                        self.assertIn(snippet, text)


if __name__ == '__main__':
    unittest.main()
