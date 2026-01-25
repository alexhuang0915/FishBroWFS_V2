import unittest
from datetime import datetime


class TestTradeDateRollover(unittest.TestCase):
    def test_cme_roll_1700_chicago_maps_to_taipei_0600_or_0700(self) -> None:
        import pandas as pd
        from zoneinfo import ZoneInfo

        from core.trade_dates import trade_days_for_ts

        chicago = ZoneInfo("America/Chicago")
        taipei = ZoneInfo("Asia/Taipei")

        # Winter (CST, UTC-6): 17:00 Chicago == next-day 07:00 Taipei
        dt_chi_winter = datetime(2024, 1, 15, 17, 0, tzinfo=chicago)
        dt_tpe_winter = dt_chi_winter.astimezone(taipei)
        self.assertEqual((dt_tpe_winter.hour, dt_tpe_winter.minute), (7, 0))

        # Summer (CDT, UTC-5): 17:00 Chicago == next-day 06:00 Taipei
        dt_chi_summer = datetime(2024, 7, 15, 17, 0, tzinfo=chicago)
        dt_tpe_summer = dt_chi_summer.astimezone(taipei)
        self.assertEqual((dt_tpe_summer.hour, dt_tpe_summer.minute), (6, 0))

        # Verify trade-date buckets flip at the roll time when using data_tz timestamps.
        # Create two timestamps: 1 minute before / after the roll (expressed in Taipei).
        for dt_tpe in (dt_tpe_winter, dt_tpe_summer):
            before = dt_tpe - pd.Timedelta(minutes=1)
            after = dt_tpe + pd.Timedelta(minutes=1)
            # Store as naive Taipei-local timestamps (this matches how our npz timestamps behave today).
            idx = pd.DatetimeIndex([before, after]).tz_localize(None)
            ts_arr = idx.to_numpy(dtype="datetime64[s]")
            trade_days = trade_days_for_ts(
                ts_arr,
                data_tz="Asia/Taipei",
                exchange_tz="America/Chicago",
                trade_date_roll_time_local="17:00",
            )
            self.assertNotEqual(trade_days[0], trade_days[1], "trade day should flip at roll time")

    def test_session_start_taipei_follows_exchange_dst(self) -> None:
        from core.trade_dates import session_start_taipei_for_instrument

        # For CME.MNQ we configured exchange_tz=America/Chicago and roll=17:00.
        # In Taipei-local time, that roll is 07:00 (winter) or 06:00 (summer).
        start_winter = session_start_taipei_for_instrument(
            datetime(2024, 1, 16, 7, 5),  # Taipei-local naive
            "CME.MNQ",
            data_tz="Asia/Taipei",
        )
        self.assertIsNotNone(start_winter)
        self.assertEqual((start_winter.hour, start_winter.minute), (7, 0))

        start_summer = session_start_taipei_for_instrument(
            datetime(2024, 7, 16, 6, 5),  # Taipei-local naive
            "CME.MNQ",
            data_tz="Asia/Taipei",
        )
        self.assertIsNotNone(start_summer)
        self.assertEqual((start_summer.hour, start_summer.minute), (6, 0))

    def test_ose_and_twf_follow_exchange_roll_and_profile_windows(self) -> None:
        from core.trade_dates import session_start_taipei_for_instrument, is_trading_time_for_instrument

        # OSE roll 15:00 Tokyo -> 14:00 Taipei
        start_ose = session_start_taipei_for_instrument(
            datetime(2024, 1, 16, 15, 0),  # Taipei-local naive (Tokyo 16:00)
            "OSE.NK225M",
            data_tz="Asia/Taipei",
        )
        self.assertIsNotNone(start_ose)
        self.assertEqual((start_ose.hour, start_ose.minute), (14, 0))

        # OSE windows are defined in Tokyo time (profile windows_tz=Asia/Tokyo).
        # Day session starts 09:45 Tokyo -> 08:45 Taipei.
        self.assertTrue(is_trading_time_for_instrument(datetime(2024, 1, 16, 9, 0), "OSE.NK225M"))
        # Break 06:00-09:45 Tokyo -> 05:00-08:45 Taipei.
        self.assertFalse(is_trading_time_for_instrument(datetime(2024, 1, 16, 6, 30), "OSE.NK225M"))

        # TWF roll is 15:00 Taipei (night session open)
        start_twf = session_start_taipei_for_instrument(datetime(2024, 1, 16, 16, 0), "TWF.MXF")
        self.assertIsNotNone(start_twf)
        self.assertEqual((start_twf.hour, start_twf.minute), (15, 0))
        # TWF breaks: 13:45-15:00 and 05:00-08:45
        self.assertFalse(is_trading_time_for_instrument(datetime(2024, 1, 16, 14, 0), "TWF.MXF"))
        self.assertTrue(is_trading_time_for_instrument(datetime(2024, 1, 16, 15, 10), "TWF.MXF"))
        self.assertFalse(is_trading_time_for_instrument(datetime(2024, 1, 16, 7, 0), "TWF.MXF"))


if __name__ == "__main__":
    unittest.main()
