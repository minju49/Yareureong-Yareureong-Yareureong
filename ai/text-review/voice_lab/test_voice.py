"""Boundary tests; actual native inference is checked separately on bundled WAV."""
import base64
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'voice_lab'),str(ROOT/'review_lab')]
from stt_engine import pcm_wave
from server import Experiment,cer
from run_batch import load_cases
from qwen_client import payload


def wav(frames=16000,rate=16000):
    target=io.BytesIO()
    with wave.open(target,'wb') as f:
        f.setparams((1,2,rate,frames,'NONE','not compressed'));f.writeframes(b'\0\0'*frames)
    return target.getvalue()


class VoiceTests(unittest.TestCase):
    def test_audio_actual_frames_not_wallclock(self):
        _,duration=pcm_wave(wav(80000));self.assertEqual(duration,5)
        for audio in (wav(100),wav(rate=48000),wav()[:-10]):
            with self.assertRaises(ValueError):pcm_wave(audio)
    def test_cer_requires_human_reference_and_preserves_hangul(self):
        self.assertIsNone(cer('   ','아아'))
        self.assertEqual(cer('두 잔!','두잔')['rate'],0)
        self.assertEqual(cer('두 잔','한 잔')['edits'],1)
    def body(self):
        audio=base64.b64encode(wav()).decode()
        return dict(wav_b64=audio,original_b64=audio,use_qwen=False,case_id='D01',
            reference_confirmed=False,reference_text='',input_source='controlled_fixture')
    def experiment(self,directory):
        exp=Experiment(directory,profile={'name':'TEST ONLY','model':'fixture','base_url':'http://127.0.0.1:1/v1'})
        exp.engine.recognize=lambda audio:{'text':'두 잔이요','inference_ms':1,'load_ms':0}
        return exp
    def test_stt_only_has_no_qwen_call_and_no_invented_accuracy(self):
        with tempfile.TemporaryDirectory() as d,patch('run_batch.request_order') as request:
            exp=self.experiment(d);r=exp.run(self.body());request.assert_not_called()
            self.assertEqual(r['status'],'completed');self.assertIsNone(r['comparison']);self.assertIsNone(r['stt_cer'])
            self.assertTrue((Path(r['experiment_dir'])/'input_16k.wav').is_file())
            self.assertEqual(r['context']['menu_id'],'vanilla_latte');self.assertIsNone(r['context']['quantity'])
    def test_raw_model_is_retained_no_gold_in_payload_same_context(self):
        requests=[]
        def fake(profile,text,context):
            requests.append(payload(profile,text,context))
            parsed={'intent':'add','items':[{'menu_id':'vanilla_latte','quantity':2,'temperature':'ice',
                'size':'regular','whipped_cream':None,'custom_note':''}],'needs_clarification':False,'clarification_question':''}
            return {'status':'ok','model_called':True,'parsed':parsed,'raw_content':'CONTROLLED FIXTURE RAW',
                'request_ms':1,'input_text':text}
        with tempfile.TemporaryDirectory() as d,patch('run_batch.request_order',side_effect=fake):
            exp=self.experiment(d);body=self.body();body['use_qwen']=True;r=exp.run(body)
            self.assertEqual(r['status'],'completed');self.assertEqual(len(requests),2)
            for q in requests:
                value=json.loads(q['messages'][1]['content'])
                self.assertEqual(set(value),{'text','context','menu'});self.assertIsNone(value['context']['quantity'])
            for b in r['comparison']['responses'].values():
                self.assertEqual(b['raw_content'],'CONTROLLED FIXTURE RAW');self.assertIsNone(b['reference_score']['correct'])
                self.assertEqual(b['gate_score'],'not_scored')
    def test_failed_stt_saved_and_processing_lock_released(self):
        with tempfile.TemporaryDirectory() as d,patch('run_batch.request_order') as request:
            exp=self.experiment(d)
            def fail(audio):raise RuntimeError('controlled STT failure')
            exp.engine.recognize=fail;r=exp.run(self.body());request.assert_not_called()
            self.assertEqual(r['status'],'failed');self.assertFalse(exp.busy)
            self.assertTrue((Path(r['experiment_dir'])/'result.json').is_file())
    def test_new_cases_have_separate_clear_references(self):
        data=load_cases(ROOT/'review_lab'/'additional20_cases.json')
        self.assertEqual(len(data['cases']),20)
        self.assertEqual(sum(c['expected_model'] is not None for c in data['cases']),16)
        self.assertEqual(sum(c['must_block'] for c in data['cases']),7)


if __name__=='__main__':unittest.main()
