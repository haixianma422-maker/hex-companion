from dataclasses import dataclass


@dataclass(frozen=True)
class Champion:
    id: int
    name: str
    slug: str
    tier: int | None
    rank: int | None

    @property
    def tier_label(self):
        return f'T{self.tier}' if self.tier is not None else '暂无档位'


@dataclass(frozen=True)
class Augment:
    id: int
    name: str
    tier: int | None
    rarity: int | None


@dataclass(frozen=True)
class Build:
    items: list[dict]
    category: str


def is_placeholder_name(name):
    """Internal game keys such as GoH_PentakillAug_Generic_BlankName are not titles."""
    return '_' in name and name.isascii() and name.replace('_', '').isalnum()


def sort_champions(champions):
    return sorted(champions, key=lambda c: (
        c.tier if c.tier is not None else 999,
        c.rank if c.rank is not None else 99999,
        c.name,
    ))


# Verified against OP.GG's rendered Jinx augment SVG badges, 2026-10-11.
OPGG_AUGMENT_LABELS = dict(enumerate('SABCDE'))


def augment_label(tier, mapping=None):
    if tier is None:
        return '暂无评级'
    return (mapping or {}).get(str(tier), OPGG_AUGMENT_LABELS.get(tier, f'第{tier + 1}档'))
