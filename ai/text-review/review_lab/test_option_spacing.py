import unittest
from option_spacing import repair_option_spacing


class OptionSpacingTests(unittest.TestCase):
    def test_observed_stt_option_splits_are_joined_without_new_letters(self):
        cases=[('차갑 게','차갑게'),('따 뜻한 카페 모카 한 잔 휘 핑 빼 고 주세요',
                                 '따뜻한 카페 모카 한 잔 휘핑 빼고 주세요'),
               ('카페 라테 따뜻 하 게 두 잔 주세요','카페 라테 따뜻하게 두 잔 주세요')]
        for source,expected in cases:
            out,spans=repair_option_spacing(source)
            self.assertEqual(out,expected)
            self.assertEqual(''.join(source.split()),''.join(out.split()))
            self.assertTrue(spans)
            for span in spans:
                self.assertEqual(source[span['start']:span['end']],span['from'])

    def test_uncertain_alias_and_other_words_are_not_joined(self):
        for text in ('아 한 잔 주세요','아 아 한 잔 주세요','차 갑 게장','휘 핑계','취 소득',
                     '따 듯한 아메리카노','아이스 아메리카노 두 잔 주세요'):
            out,spans=repair_option_spacing(text)
            self.assertEqual(out,text)
            self.assertFalse(spans)

    def test_conflicting_temperature_and_negation_survive(self):
        out,_=repair_option_spacing('따 뜻한 걸로, 아니 차갑 게 말 고 따 뜻한 걸로')
        self.assertEqual(out,'따뜻한 걸로, 아니 차갑게 말고 따뜻한 걸로')

    def test_registered_word_particles_and_unicode_whitespace(self):
        self.assertEqual(repair_option_spacing('휘\t핑은 빼\n주세요')[0],'휘핑은 빼주세요')


if __name__=='__main__': unittest.main()
