from backend.services.normalizer import normalize_name, mask_person_name

def test_normalize_name():
    assert normalize_name('ABC Construction LLC.')=='ABC CONSTRUCTION'

def test_mask():
    assert mask_person_name('John Michael Smith')=='J*** S****'
