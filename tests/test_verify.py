"""The verification engine: corroboration, fact cross-check, originality, neutrality."""
import time

from gbs.verify import checker as vc
from gbs.models import Story

NOW = time.time()


def st(src, title, summary="", h="a", age_h=0):
    return Story((h * 64)[:64], "world", src, title, summary, "https://x", NOW - age_h * 3600)


def test_independence_counts_owners_not_feeds():
    same_owner = [st("world:bbc", "Quake hits Chile"), st("sports:bbc_sport", "Quake hits Chile"),
                  st("europe:bbc_europe", "Quake hits Chile")]
    assert vc.corroborate(same_owner)["independent"] == 1 and not vc.corroborate(same_owner)["confirmed"]
    two = [st("world:bbc", "Quake hits Chile"), st("world:guardian", "Chile struck by quake")]
    c = vc.corroborate(two)
    assert c["independent"] == 2 and c["confirmed"] and c["countries"] == 1


def test_untrusted_stale_and_official_only_reports_cannot_confirm():
    assert not vc.corroborate([st("world:bbc", "x"), st("world:randomblog", "x")])["confirmed"]   # unknown outlet
    assert vc.corroborate([st("world:bbc", "x"), st("world:randomblog", "x")])["unknown_outlets"] == ["randomblog"]
    assert not vc.corroborate([st("world:bbc", "x"), st("world:dw", "x", age_h=100)])["confirmed"]  # outside window
    assert not vc.corroborate([st("world:un_news", "x"), st("science:nasa", "x")])["confirmed"]     # no news org
    assert vc.corroborate([st("world:un_news", "x"), st("world:dw", "x")])["confirmed"]


def test_cross_check_keeps_only_shared_figures():
    m = [st("world:bbc", "Quake kills 12 in Chile", "Magnitude 7.1, about 300 homes damaged."),
         st("world:dw", "Chile quake death toll at 12", "The 7.1 tremor struck at dawn; 40,000 without power.")]
    f = vc.cross_check(m)
    assert f["confirmed_numbers"] == ["12", "7.1"]
    assert set(f["unconfirmed_numbers"]) == {"300", "40000"}
    v = vc.verify("Chile earthquake leaves twelve dead, officials say",
                  "Officials in Chile say 12 people died after a magnitude 7.1 earthquake struck early in the day. "
                  "Emergency crews are searching damaged buildings, and authorities have asked residents near the "
                  "coast to stay alert for aftershocks while power is restored. 300 homes were hit.", m)
    assert not v["publish"] and any("only one source" in p for p in v["problems"])


def test_originality_catches_copying_and_headline_reuse():
    m = [st("world:bbc", "Leaders agree new climate finance deal at summit",
            "Negotiators reached agreement late on Saturday after two weeks of tense talks in Belem."),
         st("world:dw", "Climate summit ends with finance agreement", "Delegates approved the text on Saturday.")]
    copied = ("Negotiators reached agreement late on Saturday after two weeks of tense talks, ending the summit "
              "with a finance package that delegates from many nations approved before leaving for home.")
    o = vc.originality("Summit closes with deal on climate funding", copied, m)
    assert not o["ok"] and o["longest_shared_run"] >= vc.ORIG_RUN
    assert vc.originality("Climate summit ends with finance agreement", "x y z", m)["headline_reused"]
    fresh = ("Delegates at the United Nations climate meeting in Brazil approved a funding package on Saturday. "
             "Officials described the outcome as a compromise reached after long negotiations, and several "
             "countries said details on contributions will be settled next year.")
    assert vc.originality("Summit closes with deal on climate funding", fresh, m)["ok"]


def test_neutrality_flags_loaded_language():
    assert not vc.neutrality("Senator slams shocking budget!")["ok"]
    assert vc.neutrality("Senator criticises budget proposal")["ok"]
    src = [st("world:bbc", "Court convicts man on terrorist charges")]
    assert vc.neutrality("Man convicted on terrorist charges", src)["ok"]           # the charge itself, as reported
    assert not vc.neutrality("Terrorist group strikes again")["ok"]                  # our own label


def test_public_summary_never_names_sources():
    m = [st("world:bbc", "Quake hits Chile"), st("world:guardian", "Chile struck by quake")]
    v = vc.verify("Earthquake strikes Chile, officials report",
                  "Officials in Chile reported a strong earthquake on Saturday. Emergency teams are checking "
                  "buildings for damage and residents near the coast were told to follow local guidance while "
                  "authorities assess the impact across the affected region.", m)
    assert v["publish"], v["problems"]
    pub = vc.public_summary(v)
    assert pub["independent"] == 2 and pub["original"] and pub["neutral"]
    assert "bbc" not in str(pub).lower() and "guardian" not in str(pub).lower()


def test_doctor_runs_and_flags_missing_rewriter(tmp_path, capsys):
    from gbs.config import Settings
    from gbs.verify.health import doctor, registry_gaps
    cfg = Settings()
    cfg.data_dir, cfg.llm_base_url = tmp_path, ""
    assert registry_gaps() == []                 # every configured feed's outlet is in the registry
    assert doctor(cfg) == 1
    assert "rewriter: DOWN" in capsys.readouterr().out
