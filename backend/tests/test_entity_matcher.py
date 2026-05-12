from backend.services.entity_matcher import build_match_explanation, confidence_label, exact_match, fuzzy_match

def test_exact():
    m=exact_match('ABC Construction LLC',[{'entity_name':'ABC Construction','entity_type':'competitor'}])
    assert m and m['match_confidence']==100


def test_fuzzy_confidence_and_explanation():
    m=fuzzy_match('Lone Star Water Works',[{'entity_name':'Lone Star Waterworks','entity_type':'competitor'}], threshold=70)
    assert m and confidence_label(m['match_confidence']) in {'High','Medium'}
    m['matched_on_field']='contributor_employer'
    m['comparison_value']='Lone Star Water Works'
    assert 'fuzzy match' in build_match_explanation(m, 'Infrastructure Watchlist').lower()
