"""Concrete character builds: per-level stat blocks + their daily-plan policies.

A "build" pairs two things the rest of the engine keeps strictly separate:
  - DATA: a per-level stat block (LEVELS table + entity factory). What the
    character *is* at each level — attack bonus, damage, masteries, resources.
  - POLICY: a Python `decide()` implementing the daily plan. What the character
    *does* each round. See CLAUDE.md §2 (abilities are data; policies are code).

The first build is the War Angel (see design/build-guides/38_the_war_angel.txt).
"""
