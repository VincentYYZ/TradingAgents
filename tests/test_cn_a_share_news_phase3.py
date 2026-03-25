import unittest
from unittest.mock import patch

import pandas as pd

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.market_profiles import apply_market_profile


class TestChinaAShareNewsPhase3(unittest.TestCase):
    def test_apply_cn_a_share_profile_sets_china_news_vendor(self):
        config = apply_market_profile(DEFAULT_CONFIG.copy(), 'cn_a_share')
        self.assertEqual(config['data_vendors']['news_data'], 'china_news')

    def test_cn_a_share_allows_news_but_rejects_social(self):
        from tradingagents.market_profiles import validate_selected_analysts

        validate_selected_analysts('cn_a_share', ['market', 'fundamentals', 'news'])
        with self.assertRaises(ValueError):
            validate_selected_analysts('cn_a_share', ['market', 'social'])

    def test_company_news_falls_back_to_announcements_for_historical_window(self):
        from tradingagents.dataflows.china_news import get_news

        empty_company_news = pd.DataFrame(
            columns=['关键词', '新闻标题', '新闻内容', '发布时间', '文章来源', '新闻链接']
        )
        announcement_rows = pd.DataFrame([
            {
                '代码': '600519',
                '名称': '贵州茅台',
                '公告标题': '贵州茅台:2023年年度报告',
                '公告类型': '定期报告',
                '公告日期': '2024-03-30',
                '网址': 'https://example.com/notice/1',
            },
            {
                '代码': '000001',
                '名称': '平安银行',
                '公告标题': '平安银行:年度报告',
                '公告类型': '定期报告',
                '公告日期': '2024-03-30',
                '网址': 'https://example.com/notice/2',
            },
        ])

        with patch('tradingagents.dataflows.china_news.ak.stock_news_em', return_value=empty_company_news),              patch('tradingagents.dataflows.china_news.ak.stock_notice_report', return_value=announcement_rows):
            result = get_news('600519.SH', '2024-03-29', '2024-03-31')

        self.assertIn('贵州茅台:2023年年度报告', result)
        self.assertIn('定期报告', result)
        self.assertNotIn('平安银行', result)

    def test_global_news_aggregates_cctv_window_and_respects_limit(self):
        from tradingagents.dataflows.china_news import get_global_news

        def fake_news_cctv(date: str):
            if date == '20240322':
                return pd.DataFrame([
                    {'date': '20240322', 'title': '政策A', 'content': '政策A内容'},
                    {'date': '20240322', 'title': '政策B', 'content': '政策B内容'},
                ])
            if date == '20240323':
                return pd.DataFrame([
                    {'date': '20240323', 'title': '政策C', 'content': '政策C内容'},
                ])
            return pd.DataFrame(columns=['date', 'title', 'content'])

        with patch('tradingagents.dataflows.china_news.ak.news_cctv', side_effect=fake_news_cctv):
            result = get_global_news('2024-03-23', look_back_days=1, limit=2)

        self.assertIn('政策C', result)
        self.assertIn('政策A', result)
        self.assertNotIn('政策B', result)


if __name__ == '__main__':
    unittest.main()
