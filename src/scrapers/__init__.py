from src.scrapers.rightmove import RightmoveScraper, ScrapedProperty, LOCATIONS, SEARCH_CONFIGS
from src.scrapers.onthemarket import OnTheMarketScraper, OTM_LOCATIONS, OTM_SEARCH_CONFIGS
from src.scrapers.loopnet import LoopNetScraper, LOOPNET_LOCATIONS, LOOPNET_SEARCH_CONFIGS
from src.scrapers.extractors import (
    extract_unit_count,
    extract_tenure,
    extract_refurb_indicators,
    extract_red_flags,
    extract_postcode,
)

__all__ = [
    # Rightmove
    "RightmoveScraper",
    "ScrapedProperty",
    "LOCATIONS",
    "SEARCH_CONFIGS",
    # OnTheMarket
    "OnTheMarketScraper",
    "OTM_LOCATIONS",
    "OTM_SEARCH_CONFIGS",
    # LoopNet
    "LoopNetScraper",
    "LOOPNET_LOCATIONS",
    "LOOPNET_SEARCH_CONFIGS",
    # Extractors
    "extract_unit_count",
    "extract_tenure",
    "extract_refurb_indicators",
    "extract_red_flags",
    "extract_postcode",
]
