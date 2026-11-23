"""Synthetic review fixtures; they do not stand in for a user's annotations."""
import copy
import hashlib
import json
import unittest

from freeze_reference import validate_review
from review import POLICY
from run_batch import DATASET


class ReferenceReviewTests(unittest.TestCase):
    def setUp(self):
        raw=DATASET.read_bytes()
        self.data=json.loads(raw)
        self.sha=hashlib.sha256(raw).hexdigest()
        self.review={'version':'bom-human-reference-review-0.1','dataset_sha256':self.sha,
          'dataset_version':self.data['version'],'policy_version':POLICY['version'],
          'reviewer':'TEST_FIXTURE_NOT_REAL_USER','reference_state':'all_cases_approved_by_user',
          'cases':[{'case_id':c['id'],'text':c['text'],'context':c['context'],
                    'proposed_reference':copy.deepcopy(c['expected_model']),
                    'model_scoring_excluded':c['expected_model'] is None,'status':'approved'} for c in self.data['cases']]}

    def test_explicit_complete_fixture_validates(self):
        self.assertTrue(validate_review(self.review,self.data,self.sha))

    def test_no_user_or_partial_cannot_become_approved(self):
        for patch in [{'reviewer':''},{'reference_state':'partial_or_revision_required'}]:
            with self.assertRaises(ValueError): validate_review({**self.review,**patch},self.data,self.sha)

    def test_individual_unreviewed_revision_or_uncertain_blocks_freezing(self):
        for status in ['unreviewed','needs_revision','uncertain']:
            value=copy.deepcopy(self.review);value['cases'][0]['status']=status
            with self.assertRaises(ValueError): validate_review(value,self.data,self.sha)

    def test_mismatch_or_duplicate_does_not_change_gold_silently(self):
        for field,value in [('text','different'),('proposed_reference',None),('case_id','extra')]:
            review=copy.deepcopy(self.review);review['cases'][0][field]=value
            with self.assertRaises(ValueError): validate_review(review,self.data,self.sha)
        value=copy.deepcopy(self.review);value['cases'][1]=value['cases'][0]
        with self.assertRaises(ValueError): validate_review(value,self.data,self.sha)

    def test_old_dataset_or_policy_review_is_rejected(self):
        for patch in [{'dataset_sha256':'wrong'},{'policy_version':'old'}]:
            with self.assertRaises(ValueError): validate_review({**self.review,**patch},self.data,self.sha)


if __name__=='__main__': unittest.main()
