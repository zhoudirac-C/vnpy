from .vnpy_datafeed import VnpyDatafeedProvider


class QmtProvider(VnpyDatafeedProvider):
    """
    Compatibility wrapper for the old qmt provider name.

    Production code should prefer the vn.py XT/QMT datafeed or Gateway plugin.
    """

    def __init__(self) -> None:
        """"""
        super().__init__(datafeed_name="xt", provider_name="qmt")
