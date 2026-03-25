import unittest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.market_profiles import apply_market_profile


class TestChinaAShareFundamentalsPhase2(unittest.TestCase):
    def test_apply_cn_a_share_profile_sets_akshare_fundamentals_vendor(self):
        config = apply_market_profile(DEFAULT_CONFIG.copy(), 'cn_a_share')
        self.assertEqual(config['data_vendors']['fundamental_data'], 'akshare')

    def test_cn_a_share_allows_fundamentals_analyst(self):
        from tradingagents.market_profiles import validate_selected_analysts
        validate_selected_analysts('cn_a_share', ['market', 'fundamentals'])

    def test_normalize_a_share_symbol_for_em_style_vendor(self):
        from tradingagents.dataflows.ticker_normalization import normalize_symbol_for_vendor
        self.assertEqual(normalize_symbol_for_vendor('600519.SH', 'akshare_em', 'cn_a_share'), 'SH600519')
        self.assertEqual(normalize_symbol_for_vendor('000001.SZ', 'akshare_em', 'cn_a_share'), 'SZ000001')


if __name__ == '__main__':
    unittest.main()
