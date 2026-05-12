from backend.services.compliance_guard import check_question

def test_blocked():
    assert check_question('Who should we donate to?')['allowed'] is False
