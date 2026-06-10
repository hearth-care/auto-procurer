from xsource.research.validate import validate_directory_candidate

RAW = {
    "name": "D. Mortimer Tree Work",
    "phone": "07712 901234",
    "email": None,
    "profile_url": "https://www.yell.com/biz/d-mortimer-tree-work-newton-abbot-123/",
    "rating": 4.6,
    "review_count": 9,
    "town": "Newton Abbot",
    "categories": ["tree surgery"],
    "source_quote": "Rated 4.6 from 9 reviews",
}


def test_valid_yell_candidate_passes():
    c = validate_directory_candidate(RAW, site="yell.com")
    assert c is not None
    assert c.source == "yell" and c.rating_scale == 5
    assert c.phone == "+447712901234"
    assert c.source_url == RAW["profile_url"]


def test_wrong_domain_is_dropped():
    assert validate_directory_candidate({**RAW, "profile_url": "https://evil.com/x"}, site="yell.com") is None


def test_missing_profile_url_is_dropped():
    assert validate_directory_candidate({**RAW, "profile_url": None}, site="yell.com") is None


def test_out_of_scale_rating_is_nulled_not_dropped():
    c = validate_directory_candidate({**RAW, "rating": 9.4}, site="yell.com")
    assert c is not None and c.rating is None and c.review_count is None


def test_checkatrade_scale_is_10():
    raw = {**RAW, "profile_url": "https://www.checkatrade.com/trades/teigntrees", "rating": 9.4}
    c = validate_directory_candidate(raw, site="checkatrade.com")
    assert c is not None and c.rating == 9.4 and c.rating_scale == 10 and c.source == "checkatrade"


def test_bad_phone_nulled_not_dropped():
    c = validate_directory_candidate({**RAW, "phone": "call us!"}, site="yell.com")
    assert c is not None and c.phone is None
