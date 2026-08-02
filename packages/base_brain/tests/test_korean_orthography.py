# -*- coding: utf-8 -*-
from packages.base_brain.korean_orthography import has_batchim, josa, resolve_particles


def test_batchim_detection():
    assert has_batchim("사과") is False
    assert has_batchim("파이썬") is True
    assert has_batchim("서울") is True
    assert has_batchim("커피") is False


def test_josa_api():
    assert josa("사과", "topic") == "사과는"
    assert josa("파이썬", "topic") == "파이썬은"
    assert josa("고래", "subject") == "고래가"
    assert josa("책", "object") == "책을"
    assert josa("서울", "to") == "서울로"
    assert josa("집", "to") == "집으로"
    assert josa("학교", "to") == "학교로"
    assert josa("사과", "copula") == "사과예요"
    assert josa("책", "copula") == "책이에요"


def test_resolve_dual_form_placeholders():
    assert resolve_particles("사과은(는) 과일이다.") == "사과는 과일이다."
    assert resolve_particles("파이썬은(는) 언어다.") == "파이썬은 언어다."
    assert resolve_particles("고래이(가) 헤엄친다.") == "고래가 헤엄친다."
    assert resolve_particles("책을(를) 읽다.") == "책을 읽다."
    assert resolve_particles("학교(으)로 가다.") == "학교로 가다."
    assert resolve_particles("집(으)로 가다.") == "집으로 가다."
    # a sentence with no placeholder is untouched
    assert resolve_particles("커피는 음료다.") == "커피는 음료다."


def test_number_readings():
    assert resolve_particles("8은(는) 짝수.") == "8은 짝수."
    assert resolve_particles("2은(는) 짝수.") == "2는 짝수."
