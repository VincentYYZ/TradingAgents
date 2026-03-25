import unittest

from tradingagents.default_config import DEFAULT_CONFIG


class TestChinaASharePhase1(unittest.TestCase):
    def test_apply_cn_a_share_profile_sets_akshare_vendors(self):
        from tradingagents.market_profiles import apply_market_profile

        config = DEFAULT_CONFIG.copy()
        updated = apply_market_profile(config, "cn_a_share")

        self.assertEqual(updated["market_profile"], "cn_a_share")
        self.assertEqual(updated["data_vendors"]["core_stock_apis"], "akshare")
        self.assertEqual(updated["data_vendors"]["technical_indicators"], "akshare")

    def test_normalize_a_share_symbol_for_akshare(self):
        from tradingagents.dataflows.ticker_normalization import normalize_symbol_for_vendor

        self.assertEqual(normalize_symbol_for_vendor("600519.SH", "akshare", "cn_a_share"), "600519")
        self.assertEqual(normalize_symbol_for_vendor("000001.SZ", "akshare", "cn_a_share"), "000001")
        self.assertEqual(normalize_symbol_for_vendor("600519", "akshare", "cn_a_share"), "600519")

    def test_cn_a_share_rejects_social_analyst(self):
        from tradingagents.market_profiles import validate_selected_analysts

        with self.assertRaises(ValueError):
            validate_selected_analysts("cn_a_share", ["market", "social"])


if __name__ == "__main__":
    unittest.main()
