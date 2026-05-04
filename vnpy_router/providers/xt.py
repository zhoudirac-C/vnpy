from .vnpy_datafeed import VnpyDatafeedProvider


class XtProvider(VnpyDatafeedProvider):
    """
    Compatibility wrapper for the old xt provider name.

    Production code should use the vn.py XT datafeed/Gateway plugin boundary.
    """

    def __init__(self) -> None:
        """"""
        super().__init__(datafeed_name="xt", provider_name="xt")
