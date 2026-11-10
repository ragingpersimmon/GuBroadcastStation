"""Gu's verification engine: nothing is published unless it passes.

    registry   -> who each outlet is (ownership group, type, trust weight); internal only
    corroborate-> how many independent organisations report the event
    cross_check-> which facts (numbers, names) appear in 2+ independent reports
    originality-> the rewrite shares no run of words with any source text
    neutrality -> no loaded or sensational language
    feed health-> which feeds are alive

See gbs/verify/checker.py. The public sees counts and pass/fail, never sources.
"""
